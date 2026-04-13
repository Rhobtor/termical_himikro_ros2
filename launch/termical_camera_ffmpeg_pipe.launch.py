from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription(
        [
            Node(
                package="hikmicro_thermal_camera",
                executable="termical_camera_ffmpeg_pipe",
                name="rtsp_thermal_ffmpeg_pipe_node",
                output="screen",
                parameters=[
                    {
                        "url": "rtsp://admin:laentiec27@192.168.1.64:554/Streaming/Channels/101",
                        "ffmpeg_path": "/usr/bin/ffmpeg",
                        "frame_id": "thermal_optical_frame",
                        "topic_name": "/thermal/image_raw",
                        "transport": "udp",
                        "width": 640,
                        "height": 512,
                        "fps": 25.0,
                        "reconnect_delay_ms": 500,
                        "ffmpeg_log_level": "error",
                        "scale_output": False,
                    }
                ],
            )
        ]
    )
