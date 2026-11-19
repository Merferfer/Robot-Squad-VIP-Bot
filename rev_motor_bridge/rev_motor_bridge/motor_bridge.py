#!/usr/bin/env python3

import math
import socket
import threading
import time

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist


INCH = 0.0254


class MotorBridge(Node):

    def __init__(self):
        super().__init__('motor_bridge')

        self.declare_parameter('hub_ip', '192.168.43.1')
        self.declare_parameter('hub_port', 9000)
        self.declare_parameter('wheel_separation', 17.0 * INCH)
        self.declare_parameter('max_wheel_speed', 0.545)
        self.declare_parameter('max_power', 0.3)
        self.declare_parameter('command_timeout', 0.25)

        self.hub_ip = self.get_parameter('hub_ip').value
        self.hub_port = self.get_parameter('hub_port').value

        self.wheel_separation = self.get_parameter(
            'wheel_separation').value

        self.max_wheel_speed = self.get_parameter(
            'max_wheel_speed').value

        self.max_power = self.get_parameter('max_power').value
        self.command_timeout = self.get_parameter(
            'command_timeout').value

        self.left_power = 0.0
        self.right_power = 0.0

        self.last_command_time = time.monotonic()

        self.lock = threading.Lock()
        self.running = True

        self.subscription = self.create_subscription(
            Twist,
            '/cmd_vel',
            self.cmd_vel_callback,
            10
        )

        self.network_thread = threading.Thread(
            target=self.tcp_worker,
            daemon=True
        )
        self.network_thread.start()

        self.get_logger().info(
            f'Motor bridge started. Connecting to '
            f'{self.hub_ip}:{self.hub_port}'
        )

    def cmd_vel_callback(self, msg):

        v = msg.linear.x
        omega = msg.angular.z

        v_left = v - omega * self.wheel_separation / 2.0
        v_right = v + omega * self.wheel_separation / 2.0

        left = v_left / self.max_wheel_speed
        right = v_right / self.max_wheel_speed

        # Preserve the left/right ratio when limiting power.
        largest = max(abs(left), abs(right))

        if largest > self.max_power:
            scale = self.max_power / largest
            left *= scale
            right *= scale

        with self.lock:
            self.left_power = left
            self.right_power = right
            self.last_command_time = time.monotonic()

    def tcp_worker(self):

        while self.running:

            sock = None

            try:
                self.get_logger().info(
                    f'Connecting to REV Hub at '
                    f'{self.hub_ip}:{self.hub_port}'
                )

                sock = socket.create_connection(
                    (self.hub_ip, self.hub_port),
                    timeout=1.0
                )

                sock.settimeout(1.0)

                self.get_logger().info(
                    'Connected to REV Control Hub'
                )

                while self.running:

                    with self.lock:
                        left = self.left_power
                        right = self.right_power
                        last_command = self.last_command_time

                    # Stop if Nav2 stops sending commands.
                    if time.monotonic() - last_command > self.command_timeout:
                        left = 0.0
                        right = 0.0

                    message = f'CMD,{left:.3f},{right:.3f}\n'

                    sock.sendall(message.encode('utf-8'))

                    time.sleep(0.05)

            except OSError as error:

                if self.running:
                    self.get_logger().warning(
                        f'TCP connection lost: {error}. Retrying.'
                    )

                time.sleep(1.0)

            finally:

                if sock is not None:
                    try:
                        sock.sendall(b'CMD,0.000,0.000\n')
                    except OSError:
                        pass

                    sock.close()

    def destroy_node(self):

        self.running = False

        if self.network_thread.is_alive():
            self.network_thread.join(timeout=2.0)

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