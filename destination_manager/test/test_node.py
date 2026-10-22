"""Exercise state transitions with fake action futures; no Nav2 server required."""
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

pytest.importorskip('rclpy')
from action_msgs.msg import GoalStatus
from std_msgs.msg import Empty, String
from nav2_msgs.action import NavigateToPose
from destination_manager.node import DestinationManager


class Harness(DestinationManager):
    def __init__(self):
        # Skip ROS Node initialization; isolate the application state machine.
        self.frame = 'map'
        self.waypoints = {'lab': (1.0, 2.0, 0.0)}
        self.client = Mock()
        self.client.server_is_ready.return_value = True
        self.sent = Future()
        self.client.send_goal_async.return_value = self.sent
        self.events = []
        self.sequence = 0
        self.last_feedback_ns = None
        self.reset()

    def publish_status(self, state, destination=None, **details):
        self.events.append((state, destination, details))

    def get_clock(self):
        return SimpleNamespace(now=lambda: SimpleNamespace(
            to_msg=lambda: NavigateToPose.Goal().pose.header.stamp))


def request(node, name='lab'):
    node.request(String(data=name))


def accept(node):
    handle = Mock()
    handle.accepted = True
    handle.get_result_async.return_value = Future()
    handle.cancel_goal_async.return_value = Future()
    node.sent.set_result(handle)
    return handle


def finish(handle, status):
    handle.get_result_async.return_value.set_result(SimpleNamespace(
        status=status, result=SimpleNamespace(error_code=0, error_msg='')))


def test_unknown_and_unavailable():
    node = Harness()
    request(node, 'missing')
    assert node.events[-1][0] == 'unknown_destination'
    node.client.server_is_ready.return_value = False
    request(node)
    assert node.events[-1][0] == 'nav2_unavailable'
    node.client.send_goal_async.assert_not_called()


def test_busy_including_before_acceptance():
    node = Harness()
    request(node, ' LAB ')
    request(node)
    assert node.events[-1][0] == 'busy'
    assert node.client.send_goal_async.call_count == 1
    handle = accept(node)
    request(node)
    assert node.events[-1][0] == 'busy'
    finish(handle, GoalStatus.STATUS_SUCCEEDED)
    assert node.events[-1][0] == 'arrived'
    assert node.active is None


def test_cancel_while_goal_pending():
    node = Harness()
    request(node)
    node.cancel(Empty())
    assert node.events[-1][0] == 'cancel_pending'
    handle = accept(node)
    handle.cancel_goal_async.assert_called_once()
    handle.cancel_goal_async.return_value.set_result(
        SimpleNamespace(goals_canceling=[object()]))
    assert node.active == 'lab'
    finish(handle, GoalStatus.STATUS_CANCELED)
    assert node.events[-1][0] == 'canceled'
    assert node.active is None


def test_cancel_rejection_keeps_goal_active():
    node = Harness()
    request(node)
    handle = accept(node)
    node.cancel(Empty())
    handle.cancel_goal_async.return_value.set_result(
        SimpleNamespace(goals_canceling=[], return_code=1))
    assert node.events[-1][0] == 'cancel_failed'
    assert node.active == 'lab'


@pytest.mark.parametrize('status, expected', [
    (GoalStatus.STATUS_ABORTED, 'failed'),
    (GoalStatus.STATUS_CANCELED, 'canceled'),
])
def test_terminal_results(status, expected):
    node = Harness()
    request(node)
    handle = accept(node)
    finish(handle, status)
    assert node.events[-1][0] == expected
    assert node.active is None


def test_rejected_goal_clears_busy():
    node = Harness()
    request(node)
    node.sent.set_result(SimpleNamespace(accepted=False))
    assert node.events[-1][0] == 'rejected'
    assert node.active is None
