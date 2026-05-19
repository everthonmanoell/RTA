from enum import Enum, auto
import time
import logging
import config


class State(Enum):
    DETECT_MARKERS = auto()
    ALIGN_Z = auto()
    TOUCH_MARKERS = auto()
    VALIDATE_TOUCH = auto()      # usa ADB para métricas / confirmação operacional
    RESET = auto()               # botão vermelho da tela inicial
    SWIPE_TEST = auto()          # executa swipe físico
    READ_FINAL_RESULT = auto()   # lê tela final do app por marcadores fiduciais
    RETURN_TO_START = auto()     # toca na tela de falha para voltar ao início
    GO_SAFE = auto()             # manda o robô para safe pose
    SUCCESS = auto()
    ERROR = auto()


class RobotFSM:

    def __init__(self, robot, device, camera, detector, controller, auto_align, detect_red_button_fn):
        self.state = State.DETECT_MARKERS

        self.robot = robot
        self.device = device
        self.camera = camera
        self.detector = detector
        self.controller = controller
        self.auto_align = auto_align
        self.detect_red_button = detect_red_button_fn

        self.marker_infos = []
        self.current_marker_index = 0
        self.z_touch = None

    # -------------------------------------------------
    # Loop principal da FSM
    # -------------------------------------------------

    def run_step(self):
        logging.info(f"[STATE] {self.state.name}")

        if self.state == State.DETECT_MARKERS:
            self.detect_markers()

        elif self.state == State.ALIGN_Z:
            self.align_z()

        elif self.state == State.TOUCH_MARKERS:
            self.touch_marker()

        elif self.state == State.VALIDATE_TOUCH:
            self.validate_touch()

        elif self.state == State.RESET:
            self.reset()

        elif self.state == State.SWIPE_TEST:
            self.swipe_test()

        elif self.state == State.READ_FINAL_RESULT:
            self.read_final_result()

        elif self.state == State.RETURN_TO_START:
            self.return_to_start()

        elif self.state == State.GO_SAFE:
            self.go_safe()

        elif self.state == State.SUCCESS:
            logging.info("FSM finalizada com sucesso")

        elif self.state == State.ERROR:
            logging.error("FSM finalizada com erro")

    # -------------------------------------------------
    # Estado: detectar marcadores iniciais
    # -------------------------------------------------

    def detect_markers(self):
        frame = self.camera.capture_frame()

        if frame is None:
            logging.error("Falha ao capturar frame em DETECT_MARKERS")
            self.state = State.ERROR
            return

        self.marker_infos = self.detector.get_all_marker_info(frame)

        if not self.marker_infos:
            logging.warning("Nenhum marcador detectado")
            time.sleep(1)
            return

        self.current_marker_index = 0
        self.state = State.ALIGN_Z

    # -------------------------------------------------
    # Estado: alinhar Z
    # -------------------------------------------------

    def align_z(self):
        logging.info("Alinhando eixo Z...")

        try:
            self.z_touch = self.auto_align.get_touch_z()

            if self.z_touch is None:
                logging.error("Falha ao calcular Z")
                self.state = State.ERROR
                return

            logging.info(f"Z alinhado: {self.z_touch}")
            self.state = State.TOUCH_MARKERS

        except Exception as e:
            logging.error(f"Erro no ALIGN_Z: {e}")
            self.state = State.ERROR

    # -------------------------------------------------
    # Estado: tocar marcador atual
    # -------------------------------------------------

    def touch_marker(self):
        if not self.marker_infos:
            logging.error("Lista de marcadores vazia em TOUCH_MARKERS")
            self.state = State.ERROR
            return

        if self.current_marker_index >= len(self.marker_infos):
            logging.error("Marker index out of bounds in TOUCH_MARKERS")
            self.state = State.ERROR
            return

        if self.z_touch is None:
            logging.error("z_touch not defined in TOUCH_MARKERS")
            self.state = State.ERROR
            return

        marker = self.marker_infos[self.current_marker_index]
        cx, cy = marker.centroid

        logging.info(f"Tocando marcador {marker.marker_id} em ({cx}, {cy})")

        success = self.controller.touch_marker_center(
            marker, z_touch=self.z_touch)

        if success:
            self.state = State.VALIDATE_TOUCH
        else:
            logging.error(
                f"Falha ao executar toque no marcador {marker.marker_id}")
            self.state = State.ERROR

    # -------------------------------------------------
    # Estado: validar toque via ADB (métricas)
    # -------------------------------------------------

    def validate_touch(self):
        if self.current_marker_index >= len(self.marker_infos):
            logging.error("Marker index out of bounds in VALIDATE_TOUCH")
            self.state = State.ERROR
            return

        marker = self.marker_infos[self.current_marker_index]
        target = marker.centroid
        touch = self.device.wait_for_touch_feedback(timeout=3)

        if touch is not None:
            error_px = self.compute_touch_error(target, touch)

            logging.info(f"Toque detectado para marcador {marker.marker_id}")
            logging.info(
                f"Target (camera space): {target} | "
                f"Touch real (screen space): {touch} | "
                f"Erro exploratório: {error_px:.2f} px"
            )

            self.current_marker_index += 1

            if self.current_marker_index >= len(self.marker_infos):
                self.state = State.SWIPE_TEST
            else:
                self.state = State.TOUCH_MARKERS

        else:
            logging.warning("Nenhum toque detectado via ADB")
            self.state = State.RESET

    # -------------------------------------------------
    # Estado: resetar pela tela inicial (botão vermelho)
    # -------------------------------------------------

    def reset(self):
        if self.z_touch is None:
            logging.error("z_touch not defined in RESET")
            self.state = State.ERROR
            return

        frame = self.camera.capture_frame()
        if frame is None:
            logging.error("Falha ao capturar frame no RESET")
            self.state = State.ERROR
            return

        btn = self.detect_red_button(frame)

        if btn:
            logging.info(f"Touching red button at {btn}")

            success = self.controller.touch_pixel(
                btn[0], btn[1], z_touch=self.z_touch)

            if success:
                time.sleep(1)
                self.marker_infos = []
                self.current_marker_index = 0
                self.z_touch = None
                self.state = State.DETECT_MARKERS
            else:
                logging.error("Failed to touch red button")
                self.state = State.ERROR

        else:
            logging.warning("Red button not found")
            self.state = State.ERROR

    # -------------------------------------------------
    # Estado: executar swipe físico
    # -------------------------------------------------

    def swipe_test(self):
        if self.z_touch is None:
            logging.error("z_touch not defined in SWIPE_TEST")
            self.state = State.ERROR
            return

        logging.info("Iniciando swipe final...")

        grid_points = self.controller.get_grid_border_points()

        if not grid_points:
            logging.error("Could not get edge points for swipe")
            self.state = State.ERROR
            return

        success = self.controller.swipe_along_points(
            grid_points,
            z_touch=self.z_touch
        )

        if success:
            self.state = State.READ_FINAL_RESULT
        else:
            logging.error("Falha mecânica no swipe final")
            self.state = State.ERROR

    # -------------------------------------------------
    # Estado: ler tela final do app
    # -------------------------------------------------

    def read_final_result(self):
        frame = self.camera.capture_frame()
        if frame is None:
            logging.error("Falha ao capturar frame em READ_FINAL_RESULT")
            self.state = State.ERROR
            return

        marker_infos = self.detector.get_all_marker_info(frame)

        if not marker_infos:
            logging.warning("Nenhum marcador detectado na tela final")
            self.state = State.ERROR
            return

        detected_ids = [m.marker_id for m in marker_infos]
        logging.info(f"Marcadores detectados na tela final: {detected_ids}")

        if config.FINAL_FAILURE_MARKER_ID in detected_ids:
            logging.warning("App indicou FALHA no teste final")
            self.state = State.RETURN_TO_START

        elif config.FINAL_SUCCESS_MARKER_ID in detected_ids:
            logging.info("App indicou SUCESSO no teste final")
            self.state = State.GO_SAFE

        else:
            logging.warning("Nenhum marcador final conhecido foi detectado")
            self.state = State.ERROR

    # -------------------------------------------------
    # Estado: tocar na tela de falha para voltar ao início
    # -------------------------------------------------

    def return_to_start(self):
        if self.z_touch is None:
            logging.error("z_touch not defined in RETURN_TO_START")
            self.state = State.ERROR
            return

        frame = self.camera.capture_frame()
        if frame is None:
            logging.error("Could not capture frame in RETURN_TO_START")
            self.state = State.ERROR
            return

        height, width = frame.shape[:2]
        center_x = width // 2
        center_y = height // 2

        logging.info(
            f"Touching screen to return to start: ({center_x}, {center_y})")

        success = self.controller.touch_pixel(
            center_x, center_y, z_touch=self.z_touch)

        if success:
            time.sleep(1)
            self.marker_infos = []
            self.current_marker_index = 0
            self.z_touch = None
            self.state = State.DETECT_MARKERS
        else:
            logging.error("Falha ao tocar na tela para reiniciar o fluxo")
            self.state = State.ERROR

    # -------------------------------------------------
    # Estado: mover robô para safe pose
    # -------------------------------------------------

    def go_safe(self):
        logging.info("Movendo robô para safe pose...")

        try:
            if hasattr(self.robot, "move_safe"):
                self.robot.move_safe()
            elif hasattr(self.robot, "go_safe"):
                self.robot.go_safe()
            else:
                logging.error(
                    "Robot does not have move_safe() or go_safe() method")
                self.state = State.ERROR
                return

            self.state = State.SUCCESS

        except Exception as e:
            logging.error(f"Erro ao mover para safe pose: {e}")
            self.state = State.ERROR

    # -------------------------------------------------
    # Utilitário de métrica
    # -------------------------------------------------

    def compute_touch_error(self, target, actual):
        tx, ty = target
        ax, ay = actual
        return ((ax - tx) ** 2 + (ay - ty) ** 2) ** 0.5
