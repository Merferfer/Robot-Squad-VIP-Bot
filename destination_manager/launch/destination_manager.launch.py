from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    default_file = str(Path(get_package_share_directory('destination_manager'))
                       / 'config' / 'destinations.yaml')
    return LaunchDescription([
        DeclareLaunchArgument('destinations_file', default_value=default_file),
        DeclareLaunchArgument('use_sim_time', default_value='false'),
        Node(
            package='destination_manager',
            executable='destination_manager',
            output='screen',
            parameters=[{
                'destinations_file': LaunchConfiguration('destinations_file'),
                'use_sim_time': ParameterValue(
                    LaunchConfiguration('use_sim_time'), value_type=bool),
            }],
        ),
    ])
