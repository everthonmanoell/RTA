import logging

from aether_rdk import DensoRobot
from aether_rdk.datatypes import CartesianAxis, Joint, Offset3D, Pose

from abstract.abstract_robot import AbstractRobot


class Denso(AbstractRobot):
    """
    Denso robot adapter for the project.

    Responsibilities:
    - connection and arm release
    - Cartesian and joint movement
    - pose query
    - movement to safe pose
    """

    # TODO NEED TO ADJUST REAL VALUES
    # Adjust with REAL values of your safe pose
    SAFE_X = 316.87
    SAFE_Y = 14.56
    SAFE_Z = 542.34

    # If you know the exact safe orientation, keep it here.
    # If you prefer to preserve the current orientation, see move_safe() method.
    SAFE_RX = -179.75
    SAFE_RY = -3.88
    SAFE_RZ = 178.94

    # ROI (region of interest): pose for camera to see target screen.
    # Adjust these values for real setup (support, distance and inclination).
    # ROI_X = 236.12
    # ROI_Y = 7.47
    # ROI_Z = 172.85
    # ROI_RX = 179.21
    # ROI_RY = -3.18
    # ROI_RZ = 179.27
    # DEFAULT_FIG = 5

    ROI_X = 331.07
    ROI_Y = 0.62
    ROI_Z = 421.36
    ROI_RX = 180.00
    ROI_RY = 0.00
    ROI_RZ = 180.00
    DEFAULT_FIG = 5

    # motorobot ROI
    # ROI_X = 366.83
    # ROI_Y = 5.64
    # ROI_Z = 446.20
    # ROI_RX = -180.00
    # ROI_RY = 0.00
    # ROI_RZ = -180.00
    # DEFAULT_FIG = 5

    joint_pose_roi = [1.184635, 34.15339,
                      103.8132, -178.8901, -43.63271, -180.2519]

    def __init__(self, workspace_name: str, control_name: str, options: str):
        """Initialize Denso robot adapter.

        Args:
            workspace_name (str): Name of the Denso workspace.
            control_name (str): Name of the Denso control.
            options (str): Additional options string for Denso robot initialization.
        """
        self.denso_robot = DensoRobot(workspace_name, control_name, options)
        self._motor_on_state = False
        self._logger = logging.getLogger(__name__)

    def connect(self) -> bool:
        """Connect to the Denso robot.

        Returns:
            bool: True if connection successful, False otherwise.
        """
        connected = self.denso_robot.connect()
        if not connected:
            self._motor_on_state = False
        return connected

    def disconnect(self) -> bool:
        """Disconnect from the Denso robot.

        Returns:
            bool: True if disconnection successful, False otherwise.
        """
        disconnected = self.denso_robot.disconnect()
        if disconnected:
            self._motor_on_state = False
        return disconnected

    def motor_on(self) -> bool:
        """Take arm control and enable motor.

        Returns:
            bool: True if motor enabled successfully, False otherwise.
        """
        try:
            self.denso_robot.take_arm()
            self.denso_robot.robot.motor_on()
            self._motor_on_state = True
            return True
        except Exception:
            self._motor_on_state = False
            return False

    def motor_off(self) -> bool:
        """Disable motor and release arm.

        Returns:
            bool: True if motor disabled successfully, False otherwise.
        """
        try:
            self.denso_robot.robot.motor_off()
            self.denso_robot.give_arm()
            self._motor_on_state = False
            return True
        except Exception:
            return False

    def is_motor_on(self) -> bool:
        """Check if robot motor is currently enabled.

        Returns:
            bool: True if motor is enabled, False otherwise.
        """
        try:
            robot_api = self.denso_robot.robot

            if hasattr(robot_api, "motor_enabled"):
                return bool(getattr(robot_api, "motor_enabled"))

            if hasattr(robot_api, "is_motor_on"):
                is_motor_on_attr = getattr(robot_api, "is_motor_on")
                if callable(is_motor_on_attr):
                    return bool(is_motor_on_attr())
                return bool(is_motor_on_attr)
        except Exception:
            pass

        return bool(self._motor_on_state)

    def set_arm_speed(
        self,
        speed: int | float,
        accel: int | float,
        decel: int | float
    ) -> bool:
        """Set arm movement speed parameters.

        Args:
            speed (int | float): Target arm speed.
            accel (int | float): Acceleration rate.
            decel (int | float): Deceleration rate.

        Returns:
            bool: True if speed parameters set successfully, False otherwise.
        """
        return self.denso_robot.robot.set_arm_speed(speed, accel, decel)

    def create_tool_reference(self, offset_base: Offset3D, tag: str) -> bool:
        """Create a tool reference frame.

        Args:
            offset_base (Offset3D): The offset of the tool from the robot base.
            tag (str): Identifier tag for the tool reference.

        Returns:
            bool: True if tool reference created successfully, False otherwise.
        """
        return self.denso_robot.reference_frames.create_tool_reference(offset_base, tag)

    def set_current_tool_by_tag(self, tag: str) -> bool:
        """Set the current tool by its reference tag.

        Args:
            tag (str): Identifier tag of the tool reference to activate.

        Returns:
            bool: True if tool activated successfully, False otherwise.
        """
        return self.denso_robot.reference_frames.set_current_tool_by_tag(tag)

    def rotate_in_tool_reference(
        self,
        axis: CartesianAxis,
        angle_step: int | float
    ) -> bool:
        """Rotate the robot in tool reference frame.

        Args:
            axis (CartesianAxis): The axis to rotate around.
            angle_step (int | float): The rotation angle in degrees.

        Returns:
            bool: True if rotation executed successfully, False otherwise.
        """
        return self.denso_robot.reference_frames.rotate_in_tool_reference(axis, angle_step)

    def move_joints(self, command: Joint) -> bool:
        """Move robot to specified joint positions.

        Args:
            command (Joint): Target joint positions.

        Returns:
            bool: True if movement executed successfully, False otherwise.
        """
        return self.denso_robot.robot.move_joints(command)

    def move_cartesian(self, command: Pose) -> bool:
        """Move robot to specified Cartesian pose.

        Args:
            command (Pose): Target pose with x, y, z, rx, ry, rz coordinates.

        Returns:
            bool: True if movement executed successfully, False otherwise.
        """
        try:
            return self.denso_robot.robot.move_pose(command)
        except Exception as e:
            self._logger.error(
                "Failure in move_cartesian for pose x=%.3f y=%.3f z=%.3f rx=%.3f ry=%.3f rz=%.3f: %s",
                command.x,
                command.y,
                command.z,
                command.rx,
                command.ry,
                command.rz,
                e,
            )
            return False

    def get_cartesian_pose(self) -> Pose | None:
        """Get current robot Cartesian pose.

        Returns:
            Pose | None: Current pose or None if unable to retrieve.
        """
        return self.denso_robot.robot.get_pose()

    def get_joints_pose(self) -> Joint | None:
        """Get current robot joint positions.

        Returns:
            Joint | None: Current joint positions or None if unable to retrieve.
        """
        return self.denso_robot.robot.get_joints()

    def move_safe(self, preserve_orientation: bool = False) -> bool:
        """Move robot to safe pose.

        Args:
            preserve_orientation (bool): If True, preserves current orientation.
                If False, uses predefined safe orientation. Defaults to False.

        Returns:
            bool: True if movement executed successfully, False otherwise.
        """
        try:
            self.move_to_roi()
            current_pose = self.get_cartesian_pose()
            fig = current_pose.fig if current_pose is not None else self.DEFAULT_FIG

            if preserve_orientation:
                if current_pose is None:
                    return False

                safe_pose = Pose(
                    x=self.SAFE_X,
                    y=self.SAFE_Y,
                    z=self.SAFE_Z,
                    rx=current_pose.rx,
                    ry=current_pose.ry,
                    rz=current_pose.rz,
                    fig=fig,
                )
            else:
                safe_pose = Pose(
                    x=self.SAFE_X,
                    y=self.SAFE_Y,
                    z=self.SAFE_Z,
                    rx=self.SAFE_RX,
                    ry=self.SAFE_RY,
                    rz=self.SAFE_RZ,
                    fig=self.DEFAULT_FIG,
                    # fig=fig,
                )

            return self.move_cartesian(safe_pose)

        except Exception as e:
            self._logger.error("Failure in move_safe: %s", e)
            return False

    def move_to_roi(self) -> bool:
        """Move robot to ROI pose (camera pointed at device).

        Returns:
            bool: True if movement executed successfully, False otherwise.
        """
        try:
            # current_pose = self.get_cartesian_pose()
            # fig = current_pose.fig if current_pose is not None else self.DEFAULT_FIG

            roi_pose = Pose(
                x=self.ROI_X,
                y=self.ROI_Y,
                z=self.ROI_Z,
                rx=self.ROI_RX,
                ry=self.ROI_RY,
                rz=self.ROI_RZ,
                fig=self.DEFAULT_FIG,
            )
            return self.move_cartesian(roi_pose)
            # self.set_arm_speed(50, 50, 50)
            # return self.move_joints(Joint(*self.joint_pose_roi))
        except Exception as e:
            self._logger.error("Failure in move_to_roi: %s", e)
            return False
