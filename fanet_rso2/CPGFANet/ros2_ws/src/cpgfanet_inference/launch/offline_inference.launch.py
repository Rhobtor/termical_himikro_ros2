from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node
from pathlib import Path


def generate_launch_description() -> LaunchDescription:
    params_file = Path(get_package_share_directory('cpgfanet_inference')) / 'config' / 'offline_inference.params.yaml'
    return LaunchDescription(
        [
            Node(
                package='cpgfanet_inference',
                executable='offline_inference',
                name='cpgfanet_offline_inference',
                output='screen',
                parameters=[str(params_file)],
            )
        ]
    )