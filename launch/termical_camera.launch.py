from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription(
        [
            Node(
                package="hikmicro_thermal_camera",
                executable="termical_camera",
                name="rtsp_thermal_node",
                output="screen",
                parameters=[
                    {
                        "url": "rtsp://admin:laentiec27@192.168.1.64:554/Streaming/Channels/101",
                        "frame_id": "thermal_optical_frame",
                        "topic_name": "/thermal/image_raw",
                        "fps": 10.0,
                        "backend": "ffmpeg",
                        "transport": "tcp",
                        "force_mono": True,
                        "resize_width": 0,
                        "resize_height": 0,
                        "use_low_latency_ffmpeg": True,
                        "use_low_latency_gstreamer": True,
                        "gstreamer_latency_ms": 0,
                        "reconnect_delay_ms": 500,
                        "publish_latest_only": True,
                    }
                ],
            )
        ]
    )
