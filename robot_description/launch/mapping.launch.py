from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():

    # Slamtec C3 LiDAR using C1 driver
    lidar_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory('sllidar_ros2'),
                'launch',
                'sllidar_c1_launch.py'
            )
        ),
        launch_arguments={
            'serial_port': '/dev/ttyUSB0'
        }.items()
    )

    # Static transform: base_footprint -> laser
    laser_tf = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        arguments=[
            '0', '0', '0',
            '0', '0', '0',
            'base_footprint',
            'laser'
        ]
    )

    # RF2O LiDAR odometry
    rf2o = Node(
        package='rf2o_laser_odometry',
        executable='rf2o_laser_odometry_node',
        parameters=[
            os.path.expanduser('~/rf2o.yaml')
        ],
        output='screen'
    )

    # SLAM Toolbox
    slam = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory('slam_toolbox'),
                'launch',
                'online_async_launch.py'
            )
        ),
        launch_arguments={
            'slam_params_file': os.path.expanduser(
                '~/ros2_ws/src/robot_mapping/slam.yaml'
            )
        }.items()
    )

    # RViz
    rviz = Node(
        package='rviz2',
        executable='rviz2',
        output='screen'
    )

    return LaunchDescription([
        lidar_launch,
        laser_tf,
        rf2o,
        slam,
        rviz
    ])
