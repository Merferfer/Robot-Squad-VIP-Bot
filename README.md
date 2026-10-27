# Robot-Squad-VIP-Bot
The JMU 'Robot Squad' Capstone robot project for assisting navigation for visually impaired persons

# Overall Functions
The intent of this project is to create a physical robot which will guide a user around an indoor space such as a mall or school building. The interfaces include a handle with haptic feedback, a microphone/ speaker for audio I/O, and a touchscreen for settings control. 
## Core technologies
This autonomous robot will implement a Slamtec C1 lidar for prototyping. Future plans include an upgrade to the S1 for higher mapping + navigation resolution, which will allow for smoother navigation around indoor spaces. The movement will be powered by 4 DC brushless motors. The UX utilizes Ollama for processing commands. A 24V battery powers the robot, and recharges automatically by docking at a station with POGO pins to transmit power. To tie everything together, a laptop running Ubuntu 24.02 and ROS 2 Jazzy Jalisco will manage each node. Included in this repository are the custom nodes that allow for communication between certain custom devices, such as the motors and the UX.

Installation guides will be provided upon final prototyping.
