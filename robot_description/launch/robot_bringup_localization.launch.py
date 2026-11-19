#!/usr/bin/env python3
"""
Robot bringup for saved-map localization testing (ROS 2 Jazzy).

Starts:
  - robot_state_publisher (robot URDF/Xacro and fixed sensor transforms)
  - Slamtec C1 LiDAR driver
  - REV motor bridge (expected to provide odometry and odom -> base TF)
  - Nav2 localization (Map Server + AMCL)

Does NOT start:
  - SLAM Toolbox
  - Nav2 planning/controller/navigation servers

Example:
  ros2 launch <your_package> robot_bringup_localization.launch.py

Optional arguments:
  map:=/absolute/path/to/map.yaml
  params_file:=/absolute/path/to/nav2_params.yaml
  use_sim_time:=false
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
    robot_description_share = get_package_share_directory('robot_description')
    sllidar_share = get_package_share_directory('sllidar_ros2')
    nav2_bringup_share = get_package_share_directory('nav2_bringup')

    xacro_file = os.path.join(
        robot_description_share, 'urdf', 'robot.urdf.xacro'
    )

    default_map = '/home/alex-heckel/ros2_ws/config/assistive_robot_map.yaml'
    default_nav2_params = '/home/alex-heckel/ros2_ws/config/nav2_params.yaml'

    use_sim_time = LaunchConfiguration('use_sim_time')
    map_file = LaunchConfiguration('map')
    params_file = LaunchConfiguration('params_file')

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

    # Keep the same C1 launch include used by the working full bringup.
    # It may also start RViz, depending on the contents of that launch file.
    lidar = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                sllidar_share,
                'launch',
                'view_sllidar_c1_launch.py'
            )
        )
    )

    rev_motor_bridge = Node(
        package='rev_motor_bridge',
        executable='motor_bridge',
        name='motor_bridge',
        output='screen',
    )

    # Starts only the localization stack: Map Server, AMCL, and its
    # lifecycle manager. It does not start Nav2's planner/controller.
    localization = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                nav2_bringup_share,
                'launch',
                'localization_launch.py'
            )
        ),
        launch_arguments={
            'map': map_file,
            'params_file': params_file,
            'use_sim_time': use_sim_time,
            'autostart': 'true',
        }.items(),
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='false',
            description='Use simulation clock for simulation; false for the physical robot.',
        ),
        DeclareLaunchArgument(
            'map',
            default_value=default_map,
            description='Absolute path to the saved occupancy-grid map YAML.',
        ),
        DeclareLaunchArgument(
            'params_file',
            default_value=default_nav2_params,
            description='Absolute path to the Nav2 parameters YAML.',
        ),

        robot_state_publisher,
        lidar,
        rev_motor_bridge,
        localization,
    ])
