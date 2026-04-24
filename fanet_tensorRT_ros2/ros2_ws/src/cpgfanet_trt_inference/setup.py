from setuptools import find_packages, setup


package_name = 'cpgfanet_trt_inference'


setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='isa',
    maintainer_email='isa@example.com',
    description='ROS 2 Humble TensorRT topic inference node for RGB plus thermal FANet.',
    license='Proprietary',
    entry_points={
        'console_scripts': [
            'topic_inference_trt = cpgfanet_trt_inference.topic_inference_trt_node:main',
        ],
    },
)
