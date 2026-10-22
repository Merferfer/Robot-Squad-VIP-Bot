# Destination manager for ROS 2 Jazzy / Nav2

This ament_python package accepts a saved destination name and sends a
NavigateToPose action goal. It does not launch Nav2 or implement speech recognition.

## Install

Extract this package directory into ~/ros2_ws/src so the manifest is at:
~/ros2_ws/src/destination_manager/package.xml

On the robot's Ubuntu system:

```bash
source /opt/ros/jazzy/setup.bash
cd ~/ros2_ws
rosdep install --from-paths src/destination_manager --ignore-src -r -y
colcon build --symlink-install --packages-select destination_manager
source install/setup.bash
```

Use only the Jazzy underlay with this workspace. In each additional terminal,
source /opt/ros/jazzy/setup.bash then ~/ros2_ws/install/setup.bash.

## Configure destinations

Create an editable copy outside the installed package:

```bash
mkdir -p ~/ros2_ws/config
cp ~/ros2_ws/src/destination_manager/config/destinations.yaml ~/ros2_ws/config/destinations.yaml
nano ~/ros2_ws/config/destinations.yaml
```

The shipped file has NO destinations. Replace its empty mapping with real
coordinates from YOUR saved map, for example (illustrative values only):

```yaml
frame_id: map
destinations:
  lab:
    x: 3.2
    y: 1.4
    yaw: 1.57
  entrance:
    x: 0.5
    y: -2.0
    yaw: 0.0
```

x and y are meters in map, not pixels or odom coordinates. yaw is radians:
0 faces +X; pi/2 faces +Y. Use the matching saved occupancy map. Restart the
manager after editing; no rebuild is needed when using this external file.
Names are stripped of outer whitespace and matched case-insensitively.

## Start

First bring up your existing robot and Nav2 with the saved map and localization
(usually AMCL). Set the robot's initial pose and confirm localization in RViz.
Confirm the navigation action exists:

```bash
ros2 action list -t
```

Expect /navigate_to_pose [nav2_msgs/action/NavigateToPose].
Start the manager:

```bash
ros2 launch destination_manager destination_manager.launch.py destinations_file:=$HOME/ros2_ws/config/destinations.yaml
```

For Gazebo append use_sim_time:=true and ensure /clock is publishing.
Leave use_sim_time false for real hardware.

## Test without speech recognition

In another sourced terminal, start a status monitor BEFORE sending requests:

```bash
ros2 topic echo /destination_status
```

Send a destination:

```bash
ros2 topic pub --once /destination_request std_msgs/msg/String "{data: 'lab'}"
```

Cancel:

```bash
ros2 topic pub --once /destination_cancel std_msgs/msg/Empty '{}'
```

Try an unknown name and, during navigation, a second valid request to check
unknown_destination and busy handling. Run this as the sole goal sender while
testing; RViz or another Nav2 client can otherwise preempt the manager's goal.

## Interface contract

| Relative topic | Type | Payload |
| --- | --- | --- |
| destination_request | std_msgs/msg/String | Canonical destination name, e.g. lab |
| destination_cancel | std_msgs/msg/Empty | Cancel this manager's current goal |
| destination_status | std_msgs/msg/String | JSON status object |

With no namespace, these resolve to /destination_request etc.
Topics use reliable, volatile QoS with depth 10. Requests are not persisted.
Status is an event stream, not a latched state; subscribe before requesting.

Example status payload:

```json
{"state":"navigating","destination":"lab","distance_remaining_m":2.3}
```

States include ready, sending, accepted, navigating, arrived, failed, canceled,
rejected, busy, unknown_destination, nav2_unavailable, idle, cancel_pending,
canceling, cancel_failed, and error. Terminal navigation results also include
action_status and Nav2 error fields when available. Distance feedback is
published at most once per second.

New goals are rejected as busy until the prior action's final result arrives.
Canceling requests cancellation; canceled means Nav2 reported cancellation.
A cancel received before goal acknowledgment is sent after acceptance.
Transport/result errors keep the goal slot occupied if the remote state is
uncertain; check Nav2 before restarting. This initial topic interface has no
request IDs, so use one request producer. A future custom ROS action can add
per-request results and correlation without changing the waypoint lookup.

The future speech adapter should publish lab after resolving a phrase such as
"take me to the laboratory"; it should not publish raw sentences here.
It may subscribe to destination_status for spoken feedback.

## Parameters and namespacing

destinations_file: path to YAML.
action_name: relative Nav2 action name; default navigate_to_pose.
use_sim_time: standard ROS clock parameter.
Use ros2 run for custom action names/remappings:

```bash
ros2 run destination_manager destination_manager --ros-args -p destinations_file:=$HOME/ros2_ws/config/destinations.yaml -p action_name:=/robot1/navigate_to_pose
```

## Validation

```bash
cd ~/ros2_ws
colcon test --packages-select destination_manager
colcon test-result --verbose
```

Tests cover YAML validation and goal lifecycle behavior with fake action futures.
They do not replace an integration test against your running Jazzy/Nav2 system.
Stopping this node is not a guaranteed Nav2 cancel. Publish cancellation and
wait for a terminal result before stopping it; this interface is not an
emergency-stop mechanism.

Official API references:
- https://api.nav2.org/actions/jazzy/navigatetopose.html
- https://docs.ros.org/en/jazzy/Tutorials/Intermediate/Writing-an-Action-Server-Client/Py.html
