from setuptools import find_packages, setup


package_name = 'cpgfanet_inference'


setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/offline_inference.launch.py']),
        ('share/' + package_name + '/launch', ['launch/topic_pipeline.launch.py']),
        ('share/' + package_name + '/config', ['config/offline_inference.params.yaml']),
        ('share/' + package_name + '/config', ['config/topic_pipeline.params.yaml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='isa',
    maintainer_email='isa@example.com',
    description='ROS 2 Humble offline inference node for RGB plus thermal CPGFANet checkpoints.',
    license='Proprietary',
    entry_points={
        'console_scripts': [
            'offline_inference = cpgfanet_inference.offline_inference_node:main',
            'dataset_replay = cpgfanet_inference.dataset_replay_node:main',
            'topic_inference = cpgfanet_inference.topic_inference_node:main',
        ],
    },
)