import yaml
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Imu


def diag_cov(vx, vy, vz):
    """Row-major 3x3 diagonal matrix as a 9-element list."""
    return [float(vx), 0.0, 0.0,
            0.0, float(vy), 0.0,
            0.0, 0.0, float(vz)]


class ImuCovRepublisher(Node):
    def __init__(self):
        super().__init__('imu_cov_republisher')

        self.declare_parameter('input_topic', '/imu/data_raw')
        self.declare_parameter('output_topic', '/imu/data')
        self.declare_parameter('covariance_file', '/home/danieldynamics/imu_ws/src/imu_cov_republisher/config/imu.yaml')
        # Sample rate used to convert noise density to per-sample variance
        self.declare_parameter('sample_rate', 10.0)

        path = self.get_parameter('covariance_file').value
        fs = float(self.get_parameter('sample_rate').value)
        if not path:
            raise RuntimeError('Set the covariance_file parameter')

        with open(path, 'r') as f:
            cfg = yaml.safe_load(f)

        # variance = N^2 * fs
        def var(key):
            return float(cfg[key]) ** 2 * fs

        self.acc_cov = diag_cov(var('accelerometer_noise_density_x'),
                                var('accelerometer_noise_density_y'),
                                var('accelerometer_noise_density_z'))
        self.gyro_cov = diag_cov(var('gyroscope_noise_density_x'),
                                 var('gyroscope_noise_density_y'),
                                 var('gyroscope_noise_density_z'))

        self.pub = self.create_publisher(
            Imu, self.get_parameter('output_topic').value, 10)
        self.sub = self.create_subscription(
            Imu, self.get_parameter('input_topic').value, self.callback, 10)

        self.get_logger().info(f'Loaded {path}, fs = {fs} Hz')
        self.get_logger().info(f'accel cov diag: {self.acc_cov[0]:.3e}, '
                               f'{self.acc_cov[4]:.3e}, {self.acc_cov[8]:.3e}')
        self.get_logger().info(f'gyro  cov diag: {self.gyro_cov[0]:.3e}, '
                               f'{self.gyro_cov[4]:.3e}, {self.gyro_cov[8]:.3e}')

    def callback(self, msg):
        msg.angular_velocity_covariance = self.gyro_cov
        msg.linear_acceleration_covariance = self.acc_cov
        # orientation and orientation_covariance pass through unchanged
        self.pub.publish(msg)


def main():
    rclpy.init()
    node = ImuCovRepublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
