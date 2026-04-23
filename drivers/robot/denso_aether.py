import logging

from aether_rdk import DensoRobot
from aether_rdk.datatypes import CartesianAxis, Joint, Offset3D, Pose

from abstract.abstract_robot import AbstractRobot


class Denso(AbstractRobot):
    """
    Adaptador do robô Denso para o projeto.

    Responsabilidades:
    - conexão e liberação do braço
    - movimentação cartesiana e por juntas
    - consulta de pose
    - movimentação para safe pose
    """

    # TODO PRECISA AJUSTAR OS VALORES REAIS
    # Ajuste com os valores REAIS da sua pose segura
    SAFE_X = 316.87
    SAFE_Y = 14.56
    SAFE_Z = 542.34

    # Se você souber a orientação segura exata, mantenha aqui.
    # Se preferir preservar a orientação atual, veja o método move_safe().
    SAFE_RX = -179.75
    SAFE_RY = -3.88
    SAFE_RZ = 178.94

    # ROI (region of interest): pose para a camera enxergar a tela alvo.
    # Ajuste esses valores para o setup real (suporte, distancia e inclinacao).
    # ROI_X = 236.12
    # ROI_Y = 7.47
    # ROI_Z = 172.85
    # ROI_RX = 179.21
    # ROI_RY = -3.18
    # ROI_RZ = 179.27
    # DEFAULT_FIG = 5

    ROI_X = 226.39
    ROI_Y = 7.47
    ROI_Z = 226.68
    ROI_RX = 179.25
    ROI_RY = -1.60
    ROI_RZ = -179.38
    DEFAULT_FIG = 1


    joint_pose_roi = [1.184635, 34.15339, 103.8132, -178.8901, -43.63271, -180.2519]

    def __init__(self, workspace_name: str, control_name: str, options: str):
        self.denso_robot = DensoRobot(workspace_name, control_name, options)
        self._motor_on_state = False
        self._logger = logging.getLogger(__name__)

    def connect(self) -> bool:
        connected = self.denso_robot.connect()
        if not connected:
            self._motor_on_state = False
        return connected

    def disconnect(self) -> bool:
        disconnected = self.denso_robot.disconnect()
        if disconnected:
            self._motor_on_state = False
        return disconnected

    def motor_on(self) -> bool:
        """
        Toma posse do braço e liga o motor.
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
        """
        Desliga o motor e devolve o braço.
        """
        try:
            self.denso_robot.robot.motor_off()
            self.denso_robot.give_arm()
            self._motor_on_state = False
            return True
        except Exception:
            return False

    def is_motor_on(self) -> bool:
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
        return self.denso_robot.robot.set_arm_speed(speed, accel, decel)

    def create_tool_reference(self, offset_base: Offset3D, tag: str) -> bool:
        return self.denso_robot.reference_frames.create_tool_reference(offset_base, tag)

    def set_current_tool_by_tag(self, tag: str) -> bool:
        return self.denso_robot.reference_frames.set_current_tool_by_tag(tag)

    def rotate_in_tool_reference(
        self,
        axis: CartesianAxis,
        angle_step: int | float
    ) -> bool:
        return self.denso_robot.reference_frames.rotate_in_tool_reference(axis, angle_step)

    def move_joints(self, command: Joint) -> bool:
        return self.denso_robot.robot.move_joints(command)

    def move_cartesian(self, command: Pose) -> bool:
        try:
            return self.denso_robot.robot.move_pose(command)
        except Exception as e:
            self._logger.error(
                "Falha em move_cartesian para pose x=%.3f y=%.3f z=%.3f rx=%.3f ry=%.3f rz=%.3f: %s",
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
        return self.denso_robot.robot.get_pose()

    def get_joints_pose(self) -> Joint | None:
        return self.denso_robot.robot.get_joints()

    def move_safe(self, preserve_orientation: bool = False) -> bool:
        """
        Move o robô para a safe pose.

        Args:
            preserve_orientation:
                - False: usa SAFE_RX, SAFE_RY, SAFE_RZ
                - True: preserva a orientação atual e só muda x, y, z

        Returns:
            bool
        """
        try:
            self.move_to_roi()
            # current_pose = self.get_cartesian_pose()
            # fig = current_pose.fig if current_pose is not None else self.DEFAULT_FIG

            # if preserve_orientation:
            #     if current_pose is None:
            #         return False

            #     safe_pose = Pose(
            #         x=self.SAFE_X,
            #         y=self.SAFE_Y,
            #         z=self.SAFE_Z,
            #         rx=current_pose.rx,
            #         ry=current_pose.ry,
            #         rz=current_pose.rz,
            #         fig=fig,
            #     )
            # else:
            #     safe_pose = Pose(
            #         x=self.SAFE_X,
            #         y=self.SAFE_Y,
            #         z=self.SAFE_Z,
            #         rx=self.SAFE_RX,
            #         ry=self.SAFE_RY,
            #         rz=self.SAFE_RZ,
            #         fig=fig,
            #     )

            # return self.move_cartesian(safe_pose)

        except Exception as e:
            self._logger.error("Falha em move_safe: %s", e)
            return False

    def move_to_roi(self) -> bool:
        """
        Move o robô para a pose de ROI (camera apontada para o dispositivo).

        Returns:
            bool
        """
        try:
            # current_pose = self.get_cartesian_pose()
            # fig = current_pose.fig if current_pose is not None else self.DEFAULT_FIG

            # roi_pose = Pose(
            #     x=self.ROI_X,
            #     y=self.ROI_Y,
            #     z=self.ROI_Z,
            #     rx=self.ROI_RX,
            #     ry=self.ROI_RY,
            #     rz=self.ROI_RZ,
            #     fig=fig,
            # )
            # return self.move_cartesian(roi_pose)
            return self.move_joints(Joint(*self.joint_pose_roi))
        except Exception as e:
            self._logger.error("Falha em move_to_roi: %s", e)
            return False