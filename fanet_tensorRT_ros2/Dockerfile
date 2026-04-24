ARG BASE_IMAGE=dustynv/ros:humble-pytorch-l4t-r35.3.1
FROM ${BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive
ENV PATH=/usr/src/tensorrt/bin:${PATH}
SHELL ["/bin/bash", "-c"]

RUN rm -f /etc/apt/sources.list.d/ros2.list /etc/apt/sources.list.d/ros-latest.list || true && \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-pip \
    python3-colcon-common-extensions \
    libnvinfer-bin \
    libnvinfer-dev \
    libnvinfer-plugin-dev \
    python3-libnvinfer \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir onnx thop

WORKDIR /workspace/fanet_tensorRT_ros2

CMD ["bash"]
