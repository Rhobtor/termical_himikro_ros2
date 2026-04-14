ARG BASE_IMAGE=dustynv/ros:humble-pytorch-l4t-r35.3.1
FROM ${BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive
ENV ROS_WS=/workspace/CPGFANet/ros2_ws

SHELL ["/bin/bash", "-c"]

RUN if command -v curl >/dev/null 2>&1 && command -v gpg >/dev/null 2>&1; then \
    curl -fsSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key | gpg --dearmor --batch --yes -o /usr/share/keyrings/ros-archive-keyring.gpg && \
            echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu focal main" > /etc/apt/sources.list.d/ros2.list; \
        fi

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-colcon-common-extensions \
    python3-numpy \
    python3-opencv \
    python3-pil && \
    rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir thop

WORKDIR /workspace/CPGFANet

COPY . /workspace/CPGFANet

RUN source /opt/ros/humble/install/setup.bash && \
    cd ${ROS_WS} && \
    colcon build --symlink-install

CMD ["bash"]