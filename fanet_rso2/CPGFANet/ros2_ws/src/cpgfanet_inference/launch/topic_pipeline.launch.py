from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node
from pathlib import Path


def generate_launch_description() -> LaunchDescription:
    params_file = Path(get_package_share_directory('cpgfanet_inference')) / 'config' / 'topic_pipeline.params.yaml'
    return LaunchDescription(
        [
            Node(
                package='cpgfanet_inference',
                executable='dataset_replay',
                name='cpgfanet_dataset_replay',
                output='screen',
                parameters=[str(params_file)],
            ),
            Node(
                package='cpgfanet_inference',
                executable='topic_inference',
                name='cpgfanet_topic_inference',
                output='screen',
                parameters=[str(params_file)],
            ),
        ]
    )