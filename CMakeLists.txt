cmake_minimum_required(VERSION 3.5)
project(hikmicro_thermal_camera)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(cv_bridge REQUIRED)
find_package(OpenCV REQUIRED COMPONENTS core imgproc videoio)

add_executable(termical_camera src/termical_hikmicro.cpp)
ament_target_dependencies(termical_camera
  rclcpp
  sensor_msgs
  std_msgs
  cv_bridge
)
target_link_libraries(termical_camera
  ${OpenCV_LIBRARIES}
)

add_executable(termical_camera_ffmpeg_pipe src/termical_hikmicro_ffmpeg_pipe.cpp)
ament_target_dependencies(termical_camera_ffmpeg_pipe
  rclcpp
  sensor_msgs
)

install(TARGETS
  termical_camera
  termical_camera_ffmpeg_pipe
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY
  launch
  config
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
