from glob import glob
from setuptools import find_packages, setup

setup(
    name='destination_manager',
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/destination_manager']),
        ('share/destination_manager', ['package.xml', 'README.md']),
        ('share/destination_manager/config', glob('config/*.yaml')),
        ('share/destination_manager/launch', glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools', 'PyYAML'],
    zip_safe=True,
    maintainer='Alex',
    maintainer_email='alex@example.com',
    description='Translate named destinations into asynchronous Nav2 goals.',
    license='MIT',
    entry_points={'console_scripts': [
        'destination_manager = destination_manager.node:main',
    ]},
)
