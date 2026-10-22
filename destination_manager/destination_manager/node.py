"""Single-goal destination manager. Run with the default single-thread executor."""
import json
import math
from pathlib import Path

import rclpy
from action_msgs.msg import GoalStatus
from ament_index_python.packages import get_package_share_directory
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import Empty, String

from .waypoints import load_waypoints, normalize_name


class DestinationManager(Node):
    def __init__(self):
        super().__init__('destination_manager')
        default_file = str(Path(get_package_share_directory('destination_manager'))
                           / 'config' / 'destinations.yaml')
        self.declare_parameter('destinations_file', default_file)
        self.declare_parameter('action_name', 'navigate_to_pose')
        self.frame, self.waypoints = load_waypoints(
            self.get_parameter('destinations_file').value)
        self.client = ActionClient(
            self, NavigateToPose, self.get_parameter('action_name').value)
        self.status_pub = self.create_publisher(String, 'destination_status', 10)
        self.request_sub = self.create_subscription(
            String, 'destination_request', self.request, 10)
        self.cancel_sub = self.create_subscription(
            Empty, 'destination_cancel', self.cancel, 10)
        self.active = None
        self.goal_handle = None
        self.cancel_requested = False
        self.cancel_in_flight = False
        self.sequence = 0
        self.last_feedback_ns = None
        self.publish_status('ready', destinations=sorted(self.waypoints))
        self.get_logger().info(
            f'Loaded {len(self.waypoints)} destinations in frame {self.frame}')

    def publish_status(self, state, destination=None, **details):
        message = String()
        message.data = json.dumps(
            dict(state=state, destination=destination, **details))
        self.status_pub.publish(message)
        if state != 'navigating':
            self.get_logger().info(message.data)

    def reset(self):
        self.active = None
        self.goal_handle = None
        self.cancel_requested = False
        self.cancel_in_flight = False

    def request(self, message):
        name = normalize_name(message.data)
        if name not in self.waypoints:
            self.publish_status('unknown_destination', name,
                                destinations=sorted(self.waypoints))
            return
        if self.active is not None:
            self.publish_status('busy', name, active_destination=self.active)
            return
        if not self.client.server_is_ready():
            self.publish_status('nav2_unavailable', name)
            return
        x, y, yaw = self.waypoints[name]
        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = self.frame
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = x
        goal.pose.pose.position.y = y
        goal.pose.pose.orientation.z = math.sin(yaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(yaw / 2.0)
        self.active = name  # Reserve the slot BEFORE awaiting acceptance.
        self.sequence += 1
        token = self.sequence
        self.last_feedback_ns = None
        self.publish_status('sending', name)
        try:
            future = self.client.send_goal_async(
                goal, feedback_callback=lambda msg: self.feedback(msg, token))
            future.add_done_callback(lambda done: self.accepted(done, token))
        except Exception as exc:
            self.publish_status('error', name, detail=str(exc))
            self.reset()

    def current(self, token):
        return token == self.sequence and self.active is not None

    def accepted(self, future, token):
        if not self.current(token):
            return
        try:
            handle = future.result()
            if not handle.accepted:
                self.publish_status('rejected', self.active)
                self.reset()
                return
            self.goal_handle = handle
            result = handle.get_result_async()
            result.add_done_callback(lambda done: self.completed(done, token))
            self.publish_status('accepted', self.active)
            if self.cancel_requested:
                self.send_cancel()
        except Exception as exc:
            # Keep the slot occupied: the remote goal's state is uncertain.
            self.publish_status('error', self.active, detail=str(exc))

    def feedback(self, message, token):
        if not self.current(token):
            return
        now = self.get_clock().now().nanoseconds
        if (self.last_feedback_ns is not None
                and 0 <= now - self.last_feedback_ns < 1_000_000_000):
            return
        self.last_feedback_ns = now
        self.publish_status('navigating', self.active,
                            distance_remaining_m=float(
                                message.feedback.distance_remaining))

    def completed(self, future, token):
        if not self.current(token):
            return
        try:
            response = future.result()
            state = {
                GoalStatus.STATUS_SUCCEEDED: 'arrived',
                GoalStatus.STATUS_CANCELED: 'canceled',
                GoalStatus.STATUS_ABORTED: 'failed',
            }.get(response.status, 'failed')
            self.publish_status(
                state, self.active, action_status=response.status,
                error_code=int(getattr(response.result, 'error_code', 0)),
                error_msg=getattr(response.result, 'error_msg', ''))
            self.reset()
        except Exception as exc:
            self.publish_status('error', self.active, detail=str(exc))

    def cancel(self, _message):
        if self.active is None:
            self.publish_status('idle')
            return
        self.cancel_requested = True
        if self.goal_handle is None:
            self.publish_status('cancel_pending', self.active)
        else:
            self.send_cancel()

    def send_cancel(self):
        if self.cancel_in_flight:
            return
        token = self.sequence
        self.cancel_in_flight = True
        self.publish_status('canceling', self.active)
        try:
            future = self.goal_handle.cancel_goal_async()
            future.add_done_callback(lambda done: self.cancel_response(done, token))
        except Exception as exc:
            self.cancel_in_flight = False
            self.publish_status('cancel_failed', self.active, detail=str(exc))

    def cancel_response(self, future, token):
        if not self.current(token):
            return
        self.cancel_in_flight = False
        try:
            response = future.result()
            if not response.goals_canceling:
                self.cancel_requested = False
                self.publish_status('cancel_failed', self.active,
                                    return_code=int(response.return_code))
            # Remain busy until the action returns its terminal result.
        except Exception as exc:
            self.publish_status('cancel_failed', self.active, detail=str(exc))


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = DestinationManager()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
