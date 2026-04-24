cmake_minimum_required(VERSION 3.8)
project(cpgfanet_trt_gui)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(OpenCV REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)

add_executable(rgb_person_annotator src/rgb_person_annotator_node.cpp)
ament_target_dependencies(rgb_person_annotator geometry_msgs rclcpp sensor_msgs std_msgs)
target_link_libraries(rgb_person_annotator ${OpenCV_LIBS})
target_include_directories(rgb_person_annotator PRIVATE ${OpenCV_INCLUDE_DIRS})

install(TARGETS rgb_person_annotator
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()