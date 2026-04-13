#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/image_encodings.hpp>
#include <sensor_msgs/msg/image.hpp>

class RtspThermalFfmpegPipeNode : public rclcpp::Node
{
public:
  RtspThermalFfmpegPipeNode() : Node("rtsp_thermal_ffmpeg_pipe_node")
  {
    url_ = this->declare_parameter<std::string>(
      "url",
      "rtsp://admin:laentiec27@192.168.1.64:554/Streaming/Channels/101");
    ffmpeg_path_ = this->declare_parameter<std::string>("ffmpeg_path", "/usr/bin/ffmpeg");
    frame_id_ = this->declare_parameter<std::string>("frame_id", "thermal_optical_frame");
    topic_name_ = this->declare_parameter<std::string>("topic_name", "/thermal/image_raw");
    transport_ = this->declare_parameter<std::string>("transport", "udp");
    width_ = this->declare_parameter<int>("width", 640);
    height_ = this->declare_parameter<int>("height", 512);
    fps_ = this->declare_parameter<double>("fps", 25.0);
    reconnect_delay_ms_ = this->declare_parameter<int>("reconnect_delay_ms", 500);
    log_level_ = this->declare_parameter<std::string>("ffmpeg_log_level", "error");
    scale_output_ = this->declare_parameter<bool>("scale_output", false);

    if (width_ <= 0 || height_ <= 0) {
      throw std::invalid_argument("width y height deben ser mayores que cero");
    }

    pub_ = this->create_publisher<sensor_msgs::msg::Image>(
      topic_name_, rclcpp::SensorDataQoS());

    running_.store(true);
    capture_thread_ = std::thread(&RtspThermalFfmpegPipeNode::captureLoop, this);

    RCLCPP_INFO(
      this->get_logger(),
      "Leyendo RTSP por ffmpeg pipe y publicando %s desde %s",
      topic_name_.c_str(), url_.c_str());
  }

  ~RtspThermalFfmpegPipeNode() override
  {
    running_.store(false);
    if (capture_thread_.joinable()) {
      capture_thread_.join();
    }
  }

private:
  static std::string shellEscape(const std::string & value)
  {
    std::string escaped;
    escaped.reserve(value.size() + 2);
    escaped.push_back('\'');
    for (char character : value) {
      if (character == '\'') {
        escaped += "'\\''";
      } else {
        escaped.push_back(character);
      }
    }
    escaped.push_back('\'');
    return escaped;
  }

  std::string buildCommand() const
  {
    std::string filter = "format=gray";
    if (scale_output_) {
      filter = "scale=" + std::to_string(width_) + ":" + std::to_string(height_) +
        ":flags=fast_bilinear," + filter;
    }

    return
      shellEscape(ffmpeg_path_) +
      " -nostdin -hide_banner -loglevel " + shellEscape(log_level_) +
      " -rtsp_transport " + shellEscape(transport_) +
      " -fflags nobuffer+discardcorrupt -flags low_delay -an -sn -dn" +
      " -i " + shellEscape(url_) +
      " -vf " + shellEscape(filter) +
      " -pix_fmt gray -vsync 0 -f rawvideo pipe:1 2>/dev/null";
  }

  bool readExactFrame(FILE * pipe, std::vector<uint8_t> & buffer) const
  {
    size_t offset = 0;
    while (offset < buffer.size() && running_.load() && rclcpp::ok()) {
      const size_t read_count = std::fread(buffer.data() + offset, 1, buffer.size() - offset, pipe);
      if (read_count == 0) {
        return false;
      }
      offset += read_count;
    }
    return offset == buffer.size();
  }

  void captureLoop()
  {
    const size_t frame_size = static_cast<size_t>(width_) * static_cast<size_t>(height_);
    std::vector<uint8_t> frame_buffer(frame_size);
    auto min_publish_period = std::chrono::duration<double>(0.0);
    if (fps_ > 0.0) {
      min_publish_period = std::chrono::duration<double>(1.0 / fps_);
    }
    auto last_publish_time = std::chrono::steady_clock::now() - min_publish_period;

    while (running_.load() && rclcpp::ok()) {
      const std::string command = buildCommand();
      FILE * pipe = popen(command.c_str(), "r");
      if (pipe == nullptr) {
        RCLCPP_ERROR_THROTTLE(
          this->get_logger(), *this->get_clock(), 3000,
          "No se pudo lanzar ffmpeg para leer RTSP");
        std::this_thread::sleep_for(std::chrono::milliseconds(reconnect_delay_ms_));
        continue;
      }

      RCLCPP_INFO_THROTTLE(
        this->get_logger(), *this->get_clock(), 5000,
        "Capturando RTSP con ffmpeg pipe por %s", transport_.c_str());

      while (running_.load() && rclcpp::ok()) {
        if (!readExactFrame(pipe, frame_buffer)) {
          break;
        }

        const auto now = std::chrono::steady_clock::now();
        if (fps_ > 0.0 && (now - last_publish_time) < min_publish_period) {
          continue;
        }

        sensor_msgs::msg::Image msg;
        msg.header.stamp = this->now();
        msg.header.frame_id = frame_id_;
        msg.height = static_cast<uint32_t>(height_);
        msg.width = static_cast<uint32_t>(width_);
        msg.encoding = sensor_msgs::image_encodings::MONO8;
        msg.is_bigendian = false;
        msg.step = static_cast<sensor_msgs::msg::Image::_step_type>(width_);
        msg.data = frame_buffer;
        pub_->publish(msg);
        last_publish_time = now;
      }

      pclose(pipe);

      if (!running_.load() || !rclcpp::ok()) {
        break;
      }

      RCLCPP_WARN_THROTTLE(
        this->get_logger(), *this->get_clock(), 3000,
        "ffmpeg pipe se corto, reintentando conexion");
      std::this_thread::sleep_for(std::chrono::milliseconds(reconnect_delay_ms_));
    }
  }

  std::string url_;
  std::string ffmpeg_path_;
  std::string frame_id_;
  std::string topic_name_;
  std::string transport_;
  int width_;
  int height_;
  double fps_;
  int reconnect_delay_ms_;
  std::string log_level_;
  bool scale_output_;

  std::atomic<bool> running_{false};
  rclcpp::Publisher<sensor_msgs::msg::Image>::SharedPtr pub_;
  std::thread capture_thread_;
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<RtspThermalFfmpegPipeNode>();
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
