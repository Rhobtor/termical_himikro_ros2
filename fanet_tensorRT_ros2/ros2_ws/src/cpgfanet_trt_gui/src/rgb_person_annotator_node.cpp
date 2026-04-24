#include <algorithm>
#include <cmath>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include <geometry_msgs/msg/point_stamped.hpp>
#include <geometry_msgs/msg/pose_array.hpp>
#include <opencv2/imgproc.hpp>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <std_msgs/msg/float32.hpp>

class RgbPersonAnnotatorNode : public rclcpp::Node {
public:
  RgbPersonAnnotatorNode()
  : Node("fanet_rgb_person_annotator") {
    const auto rgb_topic = this->declare_parameter<std::string>("rgb_topic", "/fanet/input/rgb");
    const auto centroids_topic = this->declare_parameter<std::string>("centroids_topic", "/fanet/person_centroids");
    const auto rgb_output_topic = this->declare_parameter<std::string>("rgb_output_topic", "/fanet/gui/rgb_annotated");
    model_width_ = std::max(1, static_cast<int>(this->declare_parameter("model_width", 448)));
    model_height_ = std::max(1, static_cast<int>(this->declare_parameter("model_height", 352)));

    auto image_qos = rclcpp::QoS(rclcpp::KeepLast(1)).best_effort();

    rgb_publisher_ = this->create_publisher<sensor_msgs::msg::Image>(rgb_output_topic, image_qos);
    rgb_subscription_ = this->create_subscription<sensor_msgs::msg::Image>(
      rgb_topic,
      image_qos,
      std::bind(&RgbPersonAnnotatorNode::on_image, this, std::placeholders::_1));
    centroids_subscription_ = this->create_subscription<geometry_msgs::msg::PoseArray>(
      centroids_topic,
      10,
      std::bind(&RgbPersonAnnotatorNode::on_centroids, this, std::placeholders::_1));

    RCLCPP_INFO(
      this->get_logger(),
      "Annotator C++ activo: rgb=%s -> %s",
      rgb_topic.c_str(),
      rgb_output_topic.c_str());
  }

private:
  struct TrackingState {
    std::vector<cv::Point3d> centroids{};
  };

  void on_centroids(const geometry_msgs::msg::PoseArray::SharedPtr msg) {
    std::lock_guard<std::mutex> lock(state_mutex_);
    state_.centroids.clear();
    state_.centroids.reserve(msg->poses.size());
    for (const auto & pose : msg->poses) {
      state_.centroids.emplace_back(pose.position.x, pose.position.y, pose.position.z);
    }
  }

  void on_image(const sensor_msgs::msg::Image::SharedPtr msg) {
    if (msg->encoding != "rgb8" && msg->encoding != "bgr8") {
      RCLCPP_WARN_THROTTLE(
        this->get_logger(),
        *this->get_clock(),
        5000,
        "Encoding no soportado en annotator C++: %s",
        msg->encoding.c_str());
      return;
    }

    TrackingState snapshot;
    {
      std::lock_guard<std::mutex> lock(state_mutex_);
      snapshot = state_;
    }

    sensor_msgs::msg::Image output = *msg;
    cv::Mat image(
      static_cast<int>(output.height),
      static_cast<int>(output.width),
      CV_8UC3,
      output.data.data(),
      static_cast<size_t>(output.step));

    const auto base_color = msg->encoding == "bgr8" ? cv::Scalar(0, 220, 255) : cv::Scalar(255, 220, 0);

    for (size_t index = 0; index < snapshot.centroids.size(); ++index) {
      const auto & centroid = snapshot.centroids[index];
      const auto scaled_x = clamp_to_image(
        static_cast<int>(std::lround(centroid.x * static_cast<double>(output.width) / model_width_)),
        static_cast<int>(output.width));
      const auto scaled_y = clamp_to_image(
        static_cast<int>(std::lround(centroid.y * static_cast<double>(output.height) / model_height_)),
        static_cast<int>(output.height));
      cv::drawMarker(
        image,
        cv::Point(scaled_x, scaled_y),
        base_color,
        cv::MARKER_CROSS,
        24,
        2,
        cv::LINE_AA);

      const auto index_label = std::to_string(index + 1);
      cv::putText(
        image,
        index_label,
        cv::Point(scaled_x + 10, scaled_y + 24),
        cv::FONT_HERSHEY_SIMPLEX,
        0.6,
        base_color,
        2,
        cv::LINE_AA);
    }

    rgb_publisher_->publish(std::move(output));
  }

  static int clamp_to_image(int value, int limit) {
    return std::min(std::max(value, 0), std::max(0, limit - 1));
  }

  int model_width_{448};
  int model_height_{352};
  std::mutex state_mutex_;
  TrackingState state_;
  rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr rgb_publisher_;
  rclcpp::Subscription<sensor_msgs::msg::Image>::SharedPtr rgb_subscription_;
  rclcpp::Subscription<geometry_msgs::msg::PoseArray>::SharedPtr centroids_subscription_;
};

int main(int argc, char ** argv) {
  rclcpp::init(argc, argv);
  auto node = std::make_shared<RgbPersonAnnotatorNode>();
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}