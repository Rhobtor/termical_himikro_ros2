#include <chrono>
#include <atomic>
#include <cstdlib>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>

#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <sensor_msgs/image_encodings.hpp>
#include <std_msgs/msg/header.hpp>

#include <cv_bridge/cv_bridge.h>
#include <opencv2/opencv.hpp>

class RtspThermalNode : public rclcpp::Node
{
public:
  RtspThermalNode() : Node("rtsp_thermal_node")
  {
    url_ = this->declare_parameter<std::string>(
      "url",
      "rtsp://admin:laentiec27@192.168.1.64:554/Streaming/Channels/101");

    frame_id_ = this->declare_parameter<std::string>("frame_id", "thermal_optical_frame");
    topic_name_ = this->declare_parameter<std::string>("topic_name", "/thermal/image_raw");
    fps_ = this->declare_parameter<double>("fps", 10.0);
    backend_ = this->declare_parameter<std::string>("backend", "ffmpeg");  // ffmpeg | gstreamer | any
    transport_ = this->declare_parameter<std::string>("transport", "tcp");  // tcp | udp
    force_mono_ = this->declare_parameter<bool>("force_mono", true);
    resize_width_ = this->declare_parameter<int>("resize_width", 0);   // 0 = no resize
    resize_height_ = this->declare_parameter<int>("resize_height", 0); // 0 = no resize
    use_low_latency_ffmpeg_ = this->declare_parameter<bool>("use_low_latency_ffmpeg", true);
    use_low_latency_gstreamer_ = this->declare_parameter<bool>("use_low_latency_gstreamer", true);
    gstreamer_latency_ms_ = this->declare_parameter<int>("gstreamer_latency_ms", 0);
    reconnect_delay_ms_ = this->declare_parameter<int>("reconnect_delay_ms", 500);
    publish_latest_only_ = this->declare_parameter<bool>("publish_latest_only", true);

    pub_ = this->create_publisher<sensor_msgs::msg::Image>(
      topic_name_, rclcpp::SensorDataQoS());

    capture_api_ = cv::CAP_ANY;
    if (backend_ == "ffmpeg") {
      capture_api_ = cv::CAP_FFMPEG;
    } else if (backend_ == "gstreamer") {
      capture_api_ = cv::CAP_GSTREAMER;
    }

    if (backend_ == "ffmpeg" && use_low_latency_ffmpeg_) {
      setenv(
        "OPENCV_FFMPEG_CAPTURE_OPTIONS",
        (
          std::string("rtsp_transport;") + transport_ +
          "|max_delay;0|fflags;nobuffer|flags;low_delay|reorder_queue_size;0|probesize;32|analyzeduration;0"
        ).c_str(),
        1);
    }

    if (!openCapture()) {
      RCLCPP_FATAL(this->get_logger(), "No se pudo abrir RTSP: %s", url_.c_str());
      throw std::runtime_error("No se pudo abrir RTSP");
    }

    running_.store(true);
    capture_thread_ = std::thread(&RtspThermalNode::captureLoop, this);

    RCLCPP_INFO(this->get_logger(), "Publicando %s desde %s", topic_name_.c_str(), url_.c_str());
  }

  ~RtspThermalNode() override
  {
    running_.store(false);
    if (capture_thread_.joinable()) {
      capture_thread_.join();
    }
    if (cap_.isOpened()) {
      cap_.release();
    }
  }

private:
  bool openCapture()
  {
    if (cap_.isOpened()) {
      cap_.release();
    }

    const std::string capture_source = buildCaptureSource();
    if (!cap_.open(capture_source, capture_api_)) {
      return false;
    }

    cap_.set(cv::CAP_PROP_BUFFERSIZE, 1);
    cap_.set(cv::CAP_PROP_OPEN_TIMEOUT_MSEC, 2000.0);
    cap_.set(cv::CAP_PROP_READ_TIMEOUT_MSEC, 1000.0);
    return true;
  }

  std::string buildCaptureSource() const
  {
    if (backend_ != "gstreamer" || !use_low_latency_gstreamer_) {
      return url_;
    }

    const std::string gst_protocol = (transport_ == "udp") ? "udp" : "tcp";
    return
      "rtspsrc location=" + url_ +
      " latency=" + std::to_string(std::max(0, gstreamer_latency_ms_)) +
      " buffer-mode=none drop-on-latency=true protocols=" + gst_protocol +
      " ! queue max-size-buffers=1 leaky=downstream"
      " ! decodebin"
      " ! videoconvert"
      " ! appsink drop=true max-buffers=1 sync=false";
  }

  void captureLoop()
  {
    auto min_publish_period = std::chrono::duration<double>(0.0);
    if (fps_ > 0.0) {
      min_publish_period = std::chrono::duration<double>(1.0 / fps_);
    }
    auto last_publish_time = std::chrono::steady_clock::now() - min_publish_period;

    while (rclcpp::ok() && running_.load()) {
      cv::Mat frame;
      if (!cap_.read(frame) || frame.empty()) {
        RCLCPP_WARN_THROTTLE(
          this->get_logger(), *this->get_clock(), 3000,
          "Fallo leyendo RTSP, reintentando conexion");
        std::this_thread::sleep_for(std::chrono::milliseconds(reconnect_delay_ms_));

        if (!running_.load()) {
          break;
        }

        if (!openCapture()) {
          RCLCPP_WARN_THROTTLE(
            this->get_logger(), *this->get_clock(), 3000,
            "No se pudo reabrir RTSP: %s", url_.c_str());
        }
        continue;
      }

      const auto now = std::chrono::steady_clock::now();
      if (publish_latest_only_ && fps_ > 0.0 && (now - last_publish_time) < min_publish_period) {
        continue;
      }

      publishFrame(frame);
      last_publish_time = now;
    }
  }

  void publishFrame(cv::Mat frame)
  {
    if (frame.empty()) {
      return;
    }

    if (resize_width_ > 0 && resize_height_ > 0) {
      cv::resize(frame, frame, cv::Size(resize_width_, resize_height_));
    }

    std::string encoding;
    cv::Mat out;

    if (frame.channels() == 1) {
      out = frame;
      encoding = sensor_msgs::image_encodings::MONO8;
    } else if (frame.channels() == 3) {
      if (force_mono_) {
        cv::cvtColor(frame, out, cv::COLOR_BGR2GRAY);
        encoding = sensor_msgs::image_encodings::MONO8;
      } else {
        out = frame;
        encoding = sensor_msgs::image_encodings::BGR8;
      }
    } else if (frame.channels() == 4) {
      cv::cvtColor(frame, out, cv::COLOR_BGRA2GRAY);
      encoding = sensor_msgs::image_encodings::MONO8;
    } else {
      RCLCPP_WARN_THROTTLE(
        this->get_logger(), *this->get_clock(), 3000,
        "Número de canales no soportado: %d", frame.channels());
      return;
    }

    auto msg = cv_bridge::CvImage(std_msgs::msg::Header(), encoding, out).toImageMsg();
    msg->header.stamp = this->now();
    msg->header.frame_id = frame_id_;
    pub_->publish(*msg);
  }

  std::string url_;
  std::string frame_id_;
  std::string topic_name_;
  std::string backend_;
  std::string transport_;
  double fps_;
  bool force_mono_;
  int resize_width_;
  int resize_height_;
  bool use_low_latency_ffmpeg_;
  bool use_low_latency_gstreamer_;
  int gstreamer_latency_ms_;
  int reconnect_delay_ms_;
  bool publish_latest_only_;
  int capture_api_;

  cv::VideoCapture cap_;
  std::atomic<bool> running_{false};
  rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr pub_;
  std::thread capture_thread_;
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<RtspThermalNode>();
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
