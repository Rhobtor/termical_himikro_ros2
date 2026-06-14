FROM osrf/ros:humble-desktop

ENV DEBIAN_FRONTEND=noninteractive
ENV ROS_WS=/workspace/CPGFANet/ros2_ws
ENV PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cu128

SHELL ["/bin/bash", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-colcon-common-extensions \
    python3-opencv \
    python3-pip \
    python3-numpy \
    python3-pil \
    libgl1 \
    libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir \
    torch \
    torchvision \
    thop

WORKDIR /workspace/CPGFANet

COPY . /workspace/CPGFANet

RUN source /opt/ros/humble/setup.bash && \
    cd ${ROS_WS} && \
    colcon build --symlink-install

CMD ["bash"]