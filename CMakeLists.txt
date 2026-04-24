cmake_minimum_required(VERSION 3.5)
project(hikmicro_thermal_camera)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(cv_bridge QUIET)
find_package(OpenCV QUIET COMPONENTS core imgproc videoio)

if(cv_bridge_FOUND AND OpenCV_FOUND)
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
else()
  message(WARNING "cv_bridge/OpenCV no disponibles: se omite termical_camera y se mantiene termical_camera_ffmpeg_pipe")
endif()

add_executable(termical_camera_ffmpeg_pipe src/termical_hikmicro_ffmpeg_pipe.cpp)
ament_target_dependencies(termical_camera_ffmpeg_pipe
  rclcpp
  sensor_msgs
)

install(TARGETS
  termical_camera_ffmpeg_pipe
  DESTINATION lib/${PROJECT_NAME}
)

if(TARGET termical_camera)
  install(TARGETS
    termical_camera
    DESTINATION lib/${PROJECT_NAME}
  )
endif()

install(DIRECTORY
  launch
  config
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
