import math
import socket
import time

from geometry_msgs.msg import Quaternion, TransformStamped, Twist
from nav_msgs.msg import Odometry
import rclpy
from rclpy.node import Node
from tf2_ros import TransformBroadcaster

INCH = 0.0254  # meters per inch


class MotorBridge(Node):

    def __init__(self):
        super().__init__('motor_bridge')

        # ---- Parameters (override with --ros-args -p name:=value) ----
        self.declare_parameter('hub_ip', '192.168.43.1')
        self.declare_parameter('hub_port', 9000)
        self.declare_parameter('encoder_port', 9001)
        # 17 in track width, 3.5 in wheels.
        self.declare_parameter('wheel_separation', 17.0 * INCH)
        self.declare_parameter('wheel_diameter', 3.5 * INCH)
        # goBILDA 5203 at 50.9:1 -> 1425.1 ticks per output revolution.
        self.declare_parameter('ticks_per_rev', 1425.1)
        # Wheel speed at full power: 117 RPM * wheel circumference.
        self.declare_parameter('max_wheel_speed', 0.545)
        self.declare_parameter('odom_frame', 'odom')
        self.declare_parameter('base_frame', 'base_link')
        self.declare_parameter('publish_tf', True)

        self.hub_ip = self.get_parameter('hub_ip').value
        self.hub_port = self.get_parameter('hub_port').value
        self.encoder_port = self.get_parameter('encoder_port').value
        self.wheel_separation = self.get_parameter('wheel_separation').value
        wheel_diameter = self.get_parameter('wheel_diameter').value
        ticks_per_rev = self.get_parameter('ticks_per_rev').value
        self.max_wheel_speed = self.get_parameter('max_wheel_speed').value
        self.odom_frame = self.get_parameter('odom_frame').value
        self.base_frame = self.get_parameter('base_frame').value
        self.publish_tf = self.get_parameter('publish_tf').value

        # Distance one wheel travels per encoder tick.
        self.meters_per_tick = math.pi * wheel_diameter / ticks_per_rev

        # Same clip as the Java side.
        self.max_power = 0.3

        # Store the latest motor commands
        self.left_power = 0.0
        self.right_power = 0.0

        # Watchdog: stop if commands disappear
        self.last_command_time = time.monotonic()
        self.command_timeout = 0.25

        # UDP socket for sending commands to the hub
        self.sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM
        )

        # UDP socket for receiving encoder data from the hub (non-blocking)
        self.enc_sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM
        )
        self.enc_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.enc_sock.bind(('0.0.0.0', self.encoder_port))
        self.enc_sock.setblocking(False)

        # Odometry state
        self.x = 0.0
        self.y = 0.0
        self.yaw = 0.0
        self.prev_ticks = None  # (left_ticks, right_ticks)
        self.got_encoder_data = False

        # Publishers / broadcasters
        self.odom_pub = self.create_publisher(Odometry, '/odom', 10)
        self.tf_broadcaster = TransformBroadcaster(self)

        # Subscribe to velocity commands
        self.subscription = self.create_subscription(
            Twist,
            '/cmd_vel',
            self.cmd_vel_callback,
            10
        )

        # Send motor commands at 20 Hz
        self.timer = self.create_timer(
            0.05,
            self.send_motor_commands
        )

        # Drain the encoder socket at 100 Hz
        self.enc_timer = self.create_timer(
            0.01,
            self.read_encoders
        )

        self.get_logger().info(
            'REV motor bridge started '
            f'(separation={self.wheel_separation:.4f} m, '
            f'{self.meters_per_tick * 1000:.4f} mm/tick)'
        )

    # ------------------------------------------------------------------
    # Commands: ROS -> hub
    # ------------------------------------------------------------------
    def cmd_vel_callback(self, msg):

        v = msg.linear.x
        omega = msg.angular.z

        # Differential-drive equations
        v_left = v - omega * self.wheel_separation / 2
        v_right = v + omega * self.wheel_separation / 2

        # Convert wheel velocity to motor power
        self.left_power = max(
            -self.max_power,
            min(self.max_power, v_left / self.max_wheel_speed)
        )

        self.right_power = max(
            -self.max_power,
            min(self.max_power, v_right / self.max_wheel_speed)
        )

        self.last_command_time = time.monotonic()

    def send_motor_commands(self):

        if (
            time.monotonic() - self.last_command_time
            > self.command_timeout
        ):
            self.left_power = 0.0
            self.right_power = 0.0

        # Format: left,right
        message = (
            f"{self.left_power:.3f},"
            f"{self.right_power:.3f}"
        )

        self.sock.sendto(
            message.encode('utf-8'),
            (self.hub_ip, self.hub_port)
        )

    # ------------------------------------------------------------------
    # Encoders: hub -> ROS
    # ------------------------------------------------------------------
    def read_encoders(self):
        # Read everything that has arrived since the last call.
        while True:
            try:
                data, _ = self.enc_sock.recvfrom(256)
            except BlockingIOError:
                break
            self.handle_encoder_packet(data)

    def handle_encoder_packet(self, data):
        # Format: ENC,timestamp_ms,posLF,posLR,posRF,posRR,velLF,velLR,velRF,velRR
        try:
            parts = data.decode('utf-8').strip().split(',')
            if len(parts) != 10 or parts[0] != 'ENC':
                return
            lf, lr, rf, rr = (int(p) for p in parts[2:6])
            vlf, vlr, vrf, vrr = (float(p) for p in parts[6:10])
        except ValueError:
            return

        if not self.got_encoder_data:
            self.got_encoder_data = True
            self.get_logger().info('Receiving encoder data from hub')

        # Average the two motors on each side.
        left_ticks = (lf + lr) / 2.0
        right_ticks = (rf + rr) / 2.0

        if self.prev_ticks is None:
            self.prev_ticks = (left_ticks, right_ticks)

        d_left = (left_ticks - self.prev_ticks[0]) * self.meters_per_tick
        d_right = (right_ticks - self.prev_ticks[1]) * self.meters_per_tick
        self.prev_ticks = (left_ticks, right_ticks)

        # A jump this large is impossible at this robot's speed. It means the
        # hub opmode restarted and reset its encoders, so skip this delta.
        if abs(d_left) > 0.5 or abs(d_right) > 0.5:
            self.get_logger().warn('Encoder jump detected; re-baselining')
            return

        # Pose update (midpoint integration)
        d_center = (d_left + d_right) / 2.0
        d_yaw = (d_right - d_left) / self.wheel_separation
        self.x += d_center * math.cos(self.yaw + d_yaw / 2.0)
        self.y += d_center * math.sin(self.yaw + d_yaw / 2.0)
        self.yaw = math.atan2(
            math.sin(self.yaw + d_yaw),
            math.cos(self.yaw + d_yaw)
        )

        # Velocity from the hub's ticks/second readings
        v_left = (vlf + vlr) / 2.0 * self.meters_per_tick
        v_right = (vrf + vrr) / 2.0 * self.meters_per_tick
        v = (v_left + v_right) / 2.0
        w = (v_right - v_left) / self.wheel_separation

        self.publish_odometry(v, w)

    def publish_odometry(self, v, w):
        stamp = self.get_clock().now().to_msg()

        q = Quaternion()
        q.z = math.sin(self.yaw / 2.0)
        q.w = math.cos(self.yaw / 2.0)

        odom = Odometry()
        odom.header.stamp = stamp
        odom.header.frame_id = self.odom_frame
        odom.child_frame_id = self.base_frame
        odom.pose.pose.position.x = self.x
        odom.pose.pose.position.y = self.y
        odom.pose.pose.orientation = q
        odom.twist.twist.linear.x = v
        odom.twist.twist.angular.z = w

        # Planar robot: trust x, y, yaw; z, roll, pitch are unobservable.
        # Order is x, y, z, roll, pitch, yaw on the matrix diagonal.
        for i, value in zip(
            (0, 7, 14, 21, 28, 35),
            (0.01, 0.01, 1e6, 1e6, 1e6, 0.05)
        ):
            odom.pose.covariance[i] = value
            odom.twist.covariance[i] = value

        self.odom_pub.publish(odom)

        if self.publish_tf:
            t = TransformStamped()
            t.header.stamp = stamp
            t.header.frame_id = self.odom_frame
            t.child_frame_id = self.base_frame
            t.transform.translation.x = self.x
            t.transform.translation.y = self.y
            t.transform.rotation = q
            self.tf_broadcaster.sendTransform(t)

    def destroy_node(self):
        try:
            self.sock.sendto(
                b'0.000,0.000',
                (self.hub_ip, self.hub_port)
            )
        finally:
            self.sock.close()
            self.enc_sock.close()
            super().destroy_node()


def main(args=None):

    rclpy.init(args=args)

    node = MotorBridge()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()