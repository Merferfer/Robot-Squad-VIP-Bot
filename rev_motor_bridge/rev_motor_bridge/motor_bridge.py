import socket
import time

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist


class MotorBridge(Node):

    def __init__(self):
        super().__init__('motor_bridge')

        # REV Control Hub network settings
        self.hub_ip = '192.168.43.1'
        self.hub_port = 9000

        # Robot parameters (adjust later)
        self.wheel_separation = 0.30
        self.max_wheel_speed = 0.50

        # Store the latest motor commands
        self.left_power = 0.0
        self.right_power = 0.0

        # Watchdog: stop if commands disappear
        self.last_command_time = time.monotonic()
        self.command_timeout = 0.25

        # UDP socket
        self.sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM
        )

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

        self.get_logger().info(
            'REV motor bridge started'
        )

    def cmd_vel_callback(self, msg):

        v = msg.linear.x
        omega = msg.angular.z

        # Differential-drive equations
        v_left = v - omega * self.wheel_separation / 2
        v_right = v + omega * self.wheel_separation / 2

        # Convert wheel velocity to motor power
        self.left_power = max(
            -0.3,
            min(0.3, v_left / self.max_wheel_speed)
        )

        self.right_power = max(
            -0.3,
            min(0.3, v_right / self.max_wheel_speed)
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

    def destroy_node(self):
        try:
            self.sock.sendto(
                b'0.000,0.000',
                (self.hub_ip, self.hub_port)
            )
        finally:
            self.sock.close()
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
