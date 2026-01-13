from abc import ABC, abstractmethod
from aether_rdk.datatypes import CartesianAxis, Joint, Offset3D, Pose


class AbstractRobot(ABC):
    @abstractmethod
    def connect(self) -> bool:
        """
        Connect the robot
        :return: boolean True if connected, False otherwise
        """
        ...

    @abstractmethod
    def disconnect(self) -> bool:
        """
        Disconnect the robot
        :return: boolean True if disconnected, False otherwise
        """
        ...

    @abstractmethod
    def motor_on(self) -> bool:
        """
        Turn on the motor
        :return: True if motor is on, False otherwise
        """
        ...

    @abstractmethod
    def motor_off(self) -> bool:
        """
        Turn off the motor
        :return: True if motor is off, False otherwise
        """
        ...

    @abstractmethod
    def is_motor_on(self) -> bool:
        """
        Check if the motor is on
        :return: True if motor is on, False otherwise
        """
        ...

    @abstractmethod
    def set_arm_speed(
        self, speed: int | float, accel: int | float, decel: int | float
    ) -> bool:
        """
        Setup speed, acceleration and deceleration of the robot
        :param speed: a percentage of speed in int or float
        :param accel: a percentage of acceleration in int or float
        :param decel: a percentage of deceleration in int or float
        :return: boolean True if successful, False otherwise
        """
        ...

    @abstractmethod
    def create_tool_reference(self, offset_base: Offset3D, tag: str) -> bool:
        """
        Creates a tool reference with specific offsets for each Cartesian axis (X, Y, Z) based on a given base offset.
        :param offset_base: The base offset values (position and rotation) for defining the tool.
        :param tag: A string with an identifier for the tool being created
        :return: boolean True if successful, False otherwise
        """
        ...

    @abstractmethod
    def set_current_tool_by_tag(self, tag: str) -> bool:
        """
        Change the current tool used for movement in tool reference.
        :param tag: a string with the tag of the tool
        :return: boolean True if successful, False otherwise
        """
        ...

    @abstractmethod
    def rotate_in_tool_reference(
        self, axis: CartesianAxis, angle_step: int | float
    ) -> bool:
        """
        Rotate the robot along a specified Cartesian axis using the current tool as a reference.
        :param axis: The axis along which the robot should move (X, Y, or Z).
        :param angle_step: The step value to move along the axis. Positive values indicate forward movement, negative
        indicate backward movement.
        :return: boolean True if successful, False otherwise
        """
        ...

    @abstractmethod
    def move_joints(self, command: Joint) -> bool:
        """
        Move robot by joints angles
        :param command: a Joint with the angle of the six joints that robot will move
        :return: True if successful, False otherwise
        """
        ...

    @abstractmethod
    def move_cartesian(self, command: Pose) -> bool:
        """
        Move robot by cartesian coordinates
        :param command: a Pose with the cartesian coordinates that robot will move
        :return: True if successful, False otherwise
        """
        ...

    @abstractmethod
    def get_cartesian_pose(self) -> Pose | None:
        """
        Get current cartesian pose of the robot
        :return: Return a Pose object with the current cartesian position or None if fails
        """
        ...

    @abstractmethod
    def get_joints_pose(self) -> Joint | None: ...
