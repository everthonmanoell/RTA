from aether_rdk import DensoRobot
from aether_rdk.datatypes import CartesianAxis, Joint, Offset3D, Pose
from abstract.abstract_robot import AbstractRobot


class Denso(AbstractRobot):
    def __init__(self, workspace_name: str, control_name: str, options: str):
        self.denso_robot = DensoRobot(workspace_name, control_name, options)

    def connect(self) -> bool:
        return self.denso_robot.connect()

    def disconnect(self) -> bool:
        return self.denso_robot.disconnect()

    def motor_on(self) :
        self.denso_robot.take_arm()
        self.denso_robot.robot.motor_on()

    def motor_off(self) :
        self.denso_robot.robot.motor_off()
        self.denso_robot.give_arm()

    def is_motor_on(self) -> bool:
        return self.denso_robot.robot.motor_enabled

    def set_arm_speed(
        self, speed: int | float, accel: int | float, decel: int | float
    ) -> bool:
        return self.denso_robot.robot.set_arm_speed(speed, accel, decel)

    def create_tool_reference(self, offset_base: Offset3D, tag: str) -> bool:
        return self.denso_robot.reference_frames.create_tool_reference(offset_base, tag)

    def set_current_tool_by_tag(self, tag: str) -> bool:
        return self.denso_robot.reference_frames.set_current_tool_by_tag(tag)

    def rotate_in_tool_reference(
        self, axis: CartesianAxis, angle_step: int | float
    ) -> bool:
        return self.denso_robot.reference_frames.rotate_in_tool_reference(axis, angle_step)

    def move_joints(self, command: Joint) -> bool:
        return self.denso_robot.robot.move_joints(command)

    def move_cartesian(self, command: Pose) -> bool:
        return self.denso_robot.robot.move_pose(command)

    def get_cartesian_pose(self) -> Pose | None:
        return self.denso_robot.robot.get_pose()

    def get_joints_pose(self) -> Joint | None:
        return self.denso_robot.robot.get_joints()