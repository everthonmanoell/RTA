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
    ROI_X = 316.87
    ROI_Y = 14.56
    ROI_Z = 542.34
    ROI_RX = -179.75
    ROI_RY = -3.88
    ROI_RZ = 178.94

    def __init__(self, workspace_name: str, control_name: str, options: str):
        self.denso_robot = DensoRobot(workspace_name, control_name, options)

    def connect(self) -> bool:
        return self.denso_robot.connect()

    def disconnect(self) -> bool:
        return self.denso_robot.disconnect()

    def motor_on(self) -> bool:
        """
        Toma posse do braço e liga o motor.
        """
        try:
            self.denso_robot.take_arm()
            self.denso_robot.robot.motor_on()
            return True
        except Exception:
            return False

    def motor_off(self) -> bool:
        """
        Desliga o motor e devolve o braço.
        """
        try:
            self.denso_robot.robot.motor_off()
            self.denso_robot.give_arm()
            return True
        except Exception:
            return False

    def is_motor_on(self) -> bool:
        return self.denso_robot.robot.motor_enabled

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
        return self.denso_robot.robot.move_pose(command)

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
            if preserve_orientation:
                current_pose = self.get_cartesian_pose()
                if current_pose is None:
                    return False

                safe_pose = Pose(
                    x=self.SAFE_X,
                    y=self.SAFE_Y,
                    z=self.SAFE_Z,
                    rx=current_pose.rx,
                    ry=current_pose.ry,
                    rz=current_pose.rz,
                )
            else:
                safe_pose = Pose(
                    x=self.SAFE_X,
                    y=self.SAFE_Y,
                    z=self.SAFE_Z,
                    rx=self.SAFE_RX,
                    ry=self.SAFE_RY,
                    rz=self.SAFE_RZ,
                )

            return self.move_cartesian(safe_pose)

        except Exception:
            return False

    def move_to_roi(self) -> bool:
        """
        Move o robô para a pose de ROI (camera apontada para o dispositivo).

        Returns:
            bool
        """
        try:
            roi_pose = Pose(
                x=self.ROI_X,
                y=self.ROI_Y,
                z=self.ROI_Z,
                rx=self.ROI_RX,
                ry=self.ROI_RY,
                rz=self.ROI_RZ,
            )
            return self.move_cartesian(roi_pose)
        except Exception:
            return False