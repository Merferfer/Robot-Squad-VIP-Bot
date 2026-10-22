#!/usr/bin/env python3
"""Manual ROS 2 waypoint monitor for a robot pushed by hand.

Subscribes to AMCL's estimated position (/amcl_pose) and RViz's 2D Goal Pose
(/goal_pose). Reports straight-line distance to the selected destination and
prints "WAYPOINT REACHED" when the estimated position enters the tolerance.

Tested conceptually for ROS 2 Jazzy; requires rclpy and geometry_msgs.
This is NOT an autonomous navigation controller and does not command motors.

Run:
    source /opt/ros/jazzy/setup.bash
    source ~/ros2_ws/install/setup.bash
    python3 goal_monitor.py

In RViz2, set Fixed Frame to "map" and select a destination using the standard
"2D Goal Pose" tool configured to publish to /goal_pose.
"""

import math
import time

import rclpy
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped
from rclpy.node import Node


class GoalMonitor(Node):
    def __init__(self) -> None:
        super().__init__('goal_monitor')

        self.declare_parameter('goal_tolerance_m', 0.30)
        self.declare_parameter('pose_timeout_s', 3.0)
        self.goal_tolerance = float(self.get_parameter('goal_tolerance_m').value)
        self.pose_timeout = float(self.get_parameter('pose_timeout_s').value)

        self.position = None
        self.goal = None
        self.last_pose_time = None
        self.goal_reached = False
        self.last_wait_warning = 0.0

        self.create_subscription(
            PoseWithCovarianceStamped,
            '/amcl_pose',
            self.pose_callback,
            10,
        )
        self.create_subscription(
            PoseStamped,
            '/goal_pose',
            self.goal_callback,
            10,
        )
        self.create_timer(0.5, self.check_goal)

        self.get_logger().info(
            f'Goal monitor ready. Select a 2D Goal Pose in RViz2. '
            f'Tolerance: {self.goal_tolerance:.2f} m.'
        )

    def pose_callback(self, msg: PoseWithCovarianceStamped) -> None:
        if msg.header.frame_id.lstrip('/') != 'map':
            self.get_logger().warning(
                f'Ignoring AMCL pose in frame {msg.header.frame_id!r}; expected map.'
            )
            return
        self.position = (
            msg.pose.pose.position.x,
            msg.pose.pose.position.y,
        )
        self.last_pose_time = time.monotonic()

    def goal_callback(self, msg: PoseStamped) -> None:
        if msg.header.frame_id.lstrip('/') != 'map':
            self.get_logger().warning(
                f'Ignoring goal in frame {msg.header.frame_id!r}; expected map.'
            )
            return

        self.goal = (msg.pose.position.x, msg.pose.position.y)
        self.goal_reached = False
        self.get_logger().info(
            f'NEW WAYPOINT: x={self.goal[0]:.2f} m, y={self.goal[1]:.2f} m'
        )

    def check_goal(self) -> None:
        if self.goal is None or self.goal_reached:
            return

        now = time.monotonic()
        if self.position is None or self.last_pose_time is None or (
            now - self.last_pose_time > self.pose_timeout
        ):
            # Warn occasionally rather than flooding the terminal.
            if now - self.last_wait_warning >= 5.0:
                self.get_logger().warning('Waiting for a fresh /amcl_pose update...')
                self.last_wait_warning = now
            return

        distance = math.hypot(
            self.goal[0] - self.position[0],
            self.goal[1] - self.position[1],
        )
        self.get_logger().info(f'Distance remaining: {distance:.2f} m')

        if distance <= self.goal_tolerance:
            self.goal_reached = True
            self.get_logger().info('========== WAYPOINT REACHED ==========')


def main(args=None) -> None:
    rclpy.init(args=args)
    node = GoalMonitor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
