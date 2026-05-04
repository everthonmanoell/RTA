import threading
import logging
from drivers.device.mobile import TouchTracker, TouchRecording, map_raw_touch_to_screen

class TouchSessionRecorder:
    def __init__(self, device):
        self.device = device
        self.recording = TouchRecording()
        self.tracker = TouchTracker()
        
        self.is_listening = False
        self.thread = None
        
        # Sistema de Gatilho (Para avisar outras partes do código sobre eventos)
        self.trigger_active = False
        self.trigger_action = "down"
        self.trigger_event = None
        self.trigger_holder = None

    def start(self):
        """Inicia a gravação em background."""
        self.is_listening = True
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()

    def _listen_loop(self):
        logging.info("[TouchSessionRecorder] Iniciando escuta global de toques...")
        try:
            for evt in self.device.listener.iter_events():
                if not self.is_listening:
                    break
                
                point = self.tracker.feed(evt)
                if point:
                    # 1. Guarda tudo no histórico universal
                    self.recording.points.append(point)
                    
                    # 2. Se o gatilho estiver armado, dispara!
                    if self.trigger_active and point.action.value == self.trigger_action:
                        px = map_raw_touch_to_screen(
                            point.x, point.y, 
                            self.device.x_range, self.device.y_range, self.device.screen_size
                        )
                        if px and self.trigger_holder is not None and self.trigger_event is not None:
                            self.trigger_holder["value"] = px
                            self.trigger_event.set()
                            self.trigger_active = False # Desarma após atirar
        except Exception as e:
            logging.error(f"[TouchSessionRecorder] Erro: {e}")

    def arm_trigger(self, action: str, holder_dict: dict, thread_event: threading.Event):
        """Arma um gatilho para notificar quando uma ação específica (ex: 'down') acontecer."""
        self.trigger_action = action
        self.trigger_holder = holder_dict
        self.trigger_event = thread_event
        self.trigger_active = True

    def disarm_trigger(self):
        """Desarma o gatilho de segurança."""
        self.trigger_active = False

    def stop(self):
        """Para a gravação e espera a thread finalizar."""
        self.is_listening = False
        if self.thread:
            self.thread.join(timeout=2.0)

    def get_interaction_data(self) -> dict:
        """Retorna o dicionário completo de toques para salvar no JSON."""
        return self.recording.to_dict() if self.recording.points else None