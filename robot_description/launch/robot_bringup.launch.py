#!/usr/bin/env python3

"""
Full robot bringup for the indoor navigation robot (ROS 2 Jazzy).

Starts:
  - robot_state_publisher (loads the robot URDF/Xacro)
  - Slamtec C1 LiDAR driver
  - REV motor bridge
  - SLAM Toolbox (online asynchronous mapping)

Assumptions to verify against your workspace:
  - robot_description/urdf/robot.urdf.xacro exists
  - sllidar_ros2/launch/view_sllidar_c1_launch.py exists
  - rev_motor_bridge provides the executable "motor_bridge"
  - the REV bridge publishes odometry on /odom and the odom -> base_link TF

If your REV bridge does NOT publish odometry and the odom -> base_link
transform, SLAM Toolbox will not be able to build a map until that
odometry/TF publisher is added.
"""

import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, Command
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    # Locate installed package share directories.
    robot_description_share = get_package_share_directory('robot_description')
    sllidar_share = get_package_share_directory('sllidar_ros2')
    slam_toolbox_share = get_package_share_directory('slam_toolbox')

    # Files installed by robot_description/CMakeLists.txt.
    xacro_file = os.path.join(
        robot_description_share, 'urdf', 'robot.urdf.xacro'
    )

    # Use the standard asynchronous online mapping parameters shipped
    # with the Jazzy slam_toolbox package.
    default_slam_params = os.path.join(
        slam_toolbox_share,
        'config',
        'mapper_params_online_async.yaml'
    )

    use_sim_time = LaunchConfiguration('use_sim_time')
    slam_params_file = LaunchConfiguration('slam_params_file')

    # Expand the Xacro file into a URDF string for robot_state_publisher.
    robot_description = ParameterValue(
        Command(['xacro ', xacro_file]),
        value_type=str
    )

    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': robot_description,
            'use_sim_time': use_sim_time,
        }],
    )

    # Slamtec C1 driver. This uses the launch file that you have been
    # using to display the C1 scan in RViz.
    lidar = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                sllidar_share,
                'launch',
                'view_sllidar_c1_launch.py'
            )
        )
    )

    # The bridge is expected to receive velocity commands (normally
    # /cmd_vel) and communicate with the REV Control Hub. It should also
    # publish /odom and odom -> base_link if it is your odometry source.
    rev_motor_bridge = Node(
        package='rev_motor_bridge',
        executable='motor_bridge',
        name='motor_bridge',
        output='screen',
    )

    # Start SLAM Toolbox in online asynchronous mapping mode.
    slam_toolbox = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                slam_toolbox_share,
                'launch',
                'online_async_launch.py'
            )
        ),
        launch_arguments={
            'use_sim_time': use_sim_time,
            'slam_params_file': slam_params_file,
        }.items(),
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='false',
            description='Use simulation clock if true; otherwise use system time.',
        ),
        DeclareLaunchArgument(
            'slam_params_file',
            default_value=default_slam_params,
            description='Full path to the SLAM Toolbox parameter YAML file.',
        ),

        robot_state_publisher,
        lidar,
        rev_motor_bridge,
        slam_toolbox,
    ])
