from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Iterator, List, Optional

# ==========================================
# ADB getevent codes (Linux input protocol)
# ==========================================
_EV_ABS = "0003"
_ABS_MT_POSITION_X = "0035"
_ABS_MT_POSITION_Y = "0036"
_ABS_MT_PRESSURE = "003a"
_ABS_MT_TRACKING_ID = "0039"
_ABS_MT_TOUCH_MAJOR = "0030"
_ABS_MT_TOUCH_MINOR = "0031"

_EV_SYN = "0000"
_SYN_REPORT = "0000"

_EV_KEY = "0001"
_BTN_TOUCH = "014a"


class TouchAction(Enum):
    DOWN = "down"
    MOVE = "move"
    UP = "up"


@dataclass
class TouchPoint:
    action: TouchAction
    x: int
    y: int
    pressure: int = 0
    touch_major: int = 0
    touch_minor: int = 0
    tracking_id: int = -1
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        return {
            "action": self.action.value,
            "x": self.x,
            "y": self.y,
            "pressure": self.pressure,
            "touch_major": self.touch_major,
            "touch_minor": self.touch_minor,
            "tracking_id": self.tracking_id,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class GetEvent:
    device: str
    tipo: str
    codigo: str
    valor: str

    @property
    def valor_decimal(self) -> Optional[int]:
        try:
            return int(self.valor, 16)
        except ValueError:
            return None

    @property
    def valor_signed(self) -> Optional[int]:
        v = self.valor_decimal
        if v is not None and v >= 0x80000000:
            return v - 0x100000000
        return v

    @property
    def is_axis_x(self) -> bool:
        return self.tipo.lower() == _EV_ABS and self.codigo.lower() == _ABS_MT_POSITION_X

    @property
    def is_axis_y(self) -> bool:
        return self.tipo.lower() == _EV_ABS and self.codigo.lower() == _ABS_MT_POSITION_Y

    @property
    def is_pressure(self) -> bool:
        return self.tipo.lower() == _EV_ABS and self.codigo.lower() == _ABS_MT_PRESSURE

    @property
    def is_touch_major(self) -> bool:
        return self.tipo.lower() == _EV_ABS and self.codigo.lower() == _ABS_MT_TOUCH_MAJOR

    @property
    def is_touch_minor(self) -> bool:
        return self.tipo.lower() == _EV_ABS and self.codigo.lower() == _ABS_MT_TOUCH_MINOR

    @property
    def is_tracking_id(self) -> bool:
        return self.tipo.lower() == _EV_ABS and self.codigo.lower() == _ABS_MT_TRACKING_ID

    @property
    def is_syn_report(self) -> bool:
        return self.tipo.lower() == _EV_SYN and self.codigo.lower() == _SYN_REPORT

    @property
    def is_btn_touch(self) -> bool:
        return self.tipo.lower() == _EV_KEY and self.codigo.lower() == _BTN_TOUCH

    @property
    def is_touch_down(self) -> bool:
        return self.is_btn_touch and self.valor_decimal == 1

    @property
    def is_touch_up(self) -> bool:
        return self.is_btn_touch and self.valor_decimal == 0


def start_getevent_process() -> subprocess.Popen:
    return subprocess.Popen(
        ["adb", "shell", "getevent"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )


def parse_getevent_line(line: str) -> Optional[GetEvent]:
    raw = line.strip()
    if not raw:
        return None

    parts = raw.split()
    if len(parts) < 4:
        return None

    device = parts[0].rstrip(":")
    tipo = parts[1]
    codigo = parts[2]
    valor = parts[3]

    return GetEvent(device=device, tipo=tipo, codigo=codigo, valor=valor)


def iter_getevent_lines(proc: subprocess.Popen) -> Iterator[str]:
    assert proc.stdout is not None
    while True:
        line = proc.stdout.readline()
        if not line and proc.poll() is not None:
            break
        if line:
            yield line


def detect_touchscreen_device() -> str:
    """
    Detecta automaticamente o device touchscreen, ex: 'event9'.
    """
    try:
        output = subprocess.check_output(
            ["adb", "shell", "getevent", "-pl"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )

        current_device = ""
        has_touch_axis = False

        for line in output.splitlines():
            line = line.strip()

            if line.startswith("add device"):
                current_device = line.split("/dev/input/")[-1] if "/dev/input/" in line else ""
                has_touch_axis = False

            elif "ABS_MT_POSITION_X" in line or ("ABS_X" in line and "ABS" in line):
                has_touch_axis = True

            elif "INPUT_PROP_DIRECT" in line and has_touch_axis and current_device:
                return current_device

    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        pass

    return "event9"


def get_screen_size() -> tuple[int, int]:
    """
    Obtém a resolução física da tela via:
        adb shell wm size

    Exemplo:
        Physical size: 1080x2400
    """
    try:
        output = subprocess.check_output(
            ["adb", "shell", "wm", "size"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()

        for line in output.splitlines():
            if "Physical size:" in line:
                size_str = line.split("Physical size:")[-1].strip()
                width_str, height_str = size_str.split("x")
                return int(width_str), int(height_str)

    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, ValueError):
        pass

    return (0, 0)


def get_touch_axis_ranges(device_name: Optional[str] = None) -> tuple[tuple[int, int], tuple[int, int]]:
    """
    Retorna os ranges brutos do touchscreen:
        ((min_x, max_x), (min_y, max_y))

    Exemplo:
        ((0, 4095), (0, 4095))
    """
    if device_name is None:
        device_name = detect_touchscreen_device()

    try:
        output = subprocess.check_output(
            ["adb", "shell", "getevent", "-pl"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )

        current_device = None
        min_x = max_x = min_y = max_y = None

        for raw_line in output.splitlines():
            line = raw_line.strip()

            if line.startswith("add device"):
                current_device = line.split("/dev/input/")[-1] if "/dev/input/" in line else None

            if current_device != device_name:
                continue

            if "ABS_MT_POSITION_X" in line:
                parts = line.replace(",", "").split()
                if "min" in parts and "max" in parts:
                    min_x = int(parts[parts.index("min") + 1])
                    max_x = int(parts[parts.index("max") + 1])

            elif "ABS_MT_POSITION_Y" in line:
                parts = line.replace(",", "").split()
                if "min" in parts and "max" in parts:
                    min_y = int(parts[parts.index("min") + 1])
                    max_y = int(parts[parts.index("max") + 1])

        if None not in (min_x, max_x, min_y, max_y):
            return ((min_x, max_x), (min_y, max_y))

    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, ValueError):
        pass

    return ((0, 0), (0, 0))


def map_raw_touch_to_screen(
    raw_x: int,
    raw_y: int,
    x_range: tuple[int, int],
    y_range: tuple[int, int],
    screen_size: tuple[int, int],
) -> tuple[int, int] | None:
    """
    Converte coordenadas brutas do touchscreen para pixels reais da tela.
    """
    min_x, max_x = x_range
    min_y, max_y = y_range
    screen_w, screen_h = screen_size

    if max_x <= min_x or max_y <= min_y or screen_w <= 0 or screen_h <= 0:
        return None

    norm_x = (raw_x - min_x) / (max_x - min_x)
    norm_y = (raw_y - min_y) / (max_y - min_y)

    px = int(norm_x * (screen_w - 1))
    py = int(norm_y * (screen_h - 1))

    return (px, py)


class MobileInputListener:
    """
    Listener de eventos crus do `adb shell getevent`.
    """

    def __init__(self, device_filter: Optional[str] = None) -> None:
        if device_filter is None:
            device_filter = detect_touchscreen_device()
            print(f"[TouchListener] Auto-detected touchscreen: /dev/input/{device_filter}")
        self._device_filter = device_filter
        self._proc: Optional[subprocess.Popen] = None

    def start(self) -> None:
        if self._proc is None:
            self._proc = start_getevent_process()

    def stop(self) -> None:
        if self._proc is not None:
            try:
                self._proc.terminate()
            finally:
                self._proc = None

    def iter_events(self) -> Iterator[GetEvent]:
        if self._proc is None:
            self.start()

        assert self._proc is not None

        for line in iter_getevent_lines(self._proc):
            evt = parse_getevent_line(line)
            if not evt:
                continue
            if self._device_filter and self._device_filter not in evt.device:
                continue
            yield evt

    def run_loop(self, on_event: Callable[[GetEvent], None]) -> None:
        try:
            for evt in self.iter_events():
                on_event(evt)
        finally:
            self.stop()


class TouchTracker:
    """
    Converte stream de GetEvent em TouchPoint.
    """

    def __init__(self) -> None:
        self._x: int = 0
        self._y: int = 0
        self._pressure: int = 0
        self._touch_major: int = 0
        self._touch_minor: int = 0
        self._tracking_id: int = -1
        self._finger_down: bool = False
        self._dirty: bool = False
        self._was_down: bool = False

    def feed(self, evt: GetEvent) -> Optional[TouchPoint]:
        if evt.is_axis_x and evt.valor_decimal is not None:
            self._x = evt.valor_decimal
            self._dirty = True

        elif evt.is_axis_y and evt.valor_decimal is not None:
            self._y = evt.valor_decimal
            self._dirty = True

        elif evt.is_pressure and evt.valor_decimal is not None:
            self._pressure = evt.valor_decimal
            self._dirty = True

        elif evt.is_touch_major and evt.valor_decimal is not None:
            self._touch_major = evt.valor_decimal

        elif evt.is_touch_minor and evt.valor_decimal is not None:
            self._touch_minor = evt.valor_decimal

        elif evt.is_tracking_id:
            signed = evt.valor_signed
            if signed is not None:
                self._tracking_id = signed
                self._dirty = True

        elif evt.is_touch_down:
            self._finger_down = True
            self._dirty = True

        elif evt.is_touch_up:
            self._finger_down = False
            self._dirty = True

        elif evt.is_syn_report and self._dirty:
            self._dirty = False

            if not self._finger_down or self._tracking_id == -1:
                action = TouchAction.UP
            elif not self._was_down:
                action = TouchAction.DOWN
            else:
                action = TouchAction.MOVE

            self._was_down = self._finger_down and self._tracking_id != -1

            return TouchPoint(
                action=action,
                x=self._x,
                y=self._y,
                pressure=self._pressure,
                touch_major=self._touch_major,
                touch_minor=self._touch_minor,
                tracking_id=self._tracking_id,
                timestamp=time.time(),
            )

        return None


@dataclass
class TouchRecording:
    points: List[TouchPoint] = field(default_factory=list)

    @property
    def total_points(self) -> int:
        return len(self.points)

    @property
    def down_points(self) -> List[TouchPoint]:
        return [p for p in self.points if p.action == TouchAction.DOWN]

    @property
    def move_points(self) -> List[TouchPoint]:
        return [p for p in self.points if p.action == TouchAction.MOVE]

    @property
    def up_points(self) -> List[TouchPoint]:
        return [p for p in self.points if p.action == TouchAction.UP]

    @property
    def duration(self) -> float:
        if len(self.points) < 2:
            return 0.0
        return self.points[-1].timestamp - self.points[0].timestamp

    @property
    def x_range(self) -> tuple[int, int]:
        xs = [p.x for p in self.points if p.action != TouchAction.UP]
        return (min(xs), max(xs)) if xs else (0, 0)

    @property
    def y_range(self) -> tuple[int, int]:
        ys = [p.y for p in self.points if p.action != TouchAction.UP]
        return (min(ys), max(ys)) if ys else (0, 0)

    @property
    def avg_pressure(self) -> float:
        pts = [p.pressure for p in self.points if p.action != TouchAction.UP and p.pressure > 0]
        return sum(pts) / len(pts) if pts else 0.0

    def to_dict(self) -> dict:
        return {
            "total_points": self.total_points,
            "down_count": len(self.down_points),
            "move_count": len(self.move_points),
            "up_count": len(self.up_points),
            "duration_s": round(self.duration, 3),
            "x_range": self.x_range,
            "y_range": self.y_range,
            "avg_pressure": round(self.avg_pressure, 1),
            "points": [p.to_dict() for p in self.points],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            f.write(self.to_json())


def record_touch(
    listener: MobileInputListener,
    timeout: float = 30.0,
    stop_on_up: bool = True,
) -> TouchRecording:
    tracker = TouchTracker()
    recording = TouchRecording()
    had_down = False

    start = time.time()
    for evt in listener.iter_events():
        if time.time() - start > timeout:
            break

        point = tracker.feed(evt)
        if point:
            recording.points.append(point)
            if point.action == TouchAction.DOWN:
                had_down = True
            if stop_on_up and had_down and point.action == TouchAction.UP:
                break

    return recording


@dataclass(frozen=True)
class RTAResult:
    status: str
    hits: int
    total: int
    errors: int
    reason: str
    device_type: str

    @property
    def is_success(self) -> bool:
        return self.status == "success"

    @property
    def accuracy(self) -> float:
        return (self.hits / self.total * 100) if self.total > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "hits": self.hits,
            "total": self.total,
            "errors": self.errors,
            "reason": self.reason,
            "device_type": self.device_type,
            "accuracy": round(self.accuracy, 2),
        }


def _listen_for_rta_result(
    result_holder: list,
    stop_event: threading.Event,
    timeout: float,
) -> None:
    proc = subprocess.Popen(
        ["adb", "logcat", "-s", "RTA_RESULT:I", "-v", "raw"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    start_time = time.time()
    try:
        assert proc.stdout is not None
        while not stop_event.is_set() and time.time() - start_time < timeout:
            line = proc.stdout.readline().strip()
            if not line:
                continue
            if line.startswith("{"):
                try:
                    data = json.loads(line)
                    result_holder.append(
                        RTAResult(
                            status=data.get("status", "unknown"),
                            hits=data.get("hits", 0),
                            total=data.get("total", 0),
                            errors=data.get("errors", 0),
                            reason=data.get("reason", ""),
                            device_type=data.get("device_type", ""),
                        )
                    )
                    stop_event.set()
                    return
                except json.JSONDecodeError:
                    continue
    finally:
        proc.terminate()
        proc.wait()


def wait_for_rta_result(timeout: float = 120.0) -> Optional[RTAResult]:
    subprocess.run(["adb", "logcat", "-c"], capture_output=True)

    result_holder: list[RTAResult] = []
    stop = threading.Event()
    _listen_for_rta_result(result_holder, stop, timeout)
    return result_holder[0] if result_holder else None


def get_device_model() -> str:
    try:
        brand = subprocess.check_output(
            ["adb", "shell", "getprop", "ro.product.brand"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()

        model = subprocess.check_output(
            ["adb", "shell", "getprop", "ro.product.model"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()

        if brand and model.lower().startswith(brand.lower()):
            return model

        return f"{brand} {model}" if brand else model

    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        return "unknown"


@dataclass
class RTATestResult:
    test_id: str
    timestamp: str
    device_model: str
    device_type: str
    touch_recording: TouchRecording
    app_result: Optional[RTAResult]
    duration_s: float

    def to_dict(self) -> dict:
        return {
            "test_id": self.test_id,
            "timestamp": self.timestamp,
            "device_model": self.device_model,
            "device_type": self.device_type,
            "duration_s": round(self.duration_s, 3),
            "app_result": self.app_result.to_dict() if self.app_result else None,
            "touch": self.touch_recording.to_dict(),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            f.write(self.to_json())

    def summary(self) -> str:
        status = self.app_result.status if self.app_result else "timeout"
        hits = self.app_result.hits if self.app_result else 0
        total = self.app_result.total if self.app_result else 0
        errors = self.app_result.errors if self.app_result else 0
        acc = self.app_result.accuracy if self.app_result else 0.0
        return (
            f"Test {self.test_id} | {self.device_model} | {status.upper()} | "
            f"Hits: {hits}/{total} ({acc:.1f}%) | "
            f"Errors: {errors} | "
            f"Touch points: {self.touch_recording.total_points} | "
            f"Duration: {self.duration_s:.1f}s"
        )


def run_rta_test(
    output_dir: str = "test_results",
    device_type: str = "flat",
    device_model: Optional[str] = None,
    timeout: float = 120.0,
    test_id: Optional[str] = None,
) -> RTATestResult:
    now = datetime.now()
    if test_id is None:
        test_id = f"test_{now.strftime('%Y%m%d_%H%M%S')}"
    timestamp = now.isoformat()

    if device_model is None:
        device_model = get_device_model()

    print(f"[RTA Test] Starting test: {test_id}")
    print(f"[RTA Test] Device model: {device_model}")
    print(f"[RTA Test] Device type: {device_type}")

    subprocess.run(["adb", "logcat", "-c"], capture_output=True)

    result_holder: list[RTAResult] = []
    stop_event = threading.Event()
    logcat_thread = threading.Thread(
        target=_listen_for_rta_result,
        args=(result_holder, stop_event, timeout),
        daemon=True,
    )
    logcat_thread.start()

    subprocess.run(
        [
            "adb", "shell", "am", "start", "-n",
            "com.example.rta/.MainActivity",
            "--es", "device_type", device_type,
        ],
        capture_output=True,
    )
    print("[RTA Test] App launched. Recording touches...")

    listener = MobileInputListener()
    tracker = TouchTracker()
    recording = TouchRecording()
    start_time = time.time()

    try:
        for evt in listener.iter_events():
            if stop_event.is_set():
                break
            if time.time() - start_time > timeout:
                break

            point = tracker.feed(evt)
            if point:
                recording.points.append(point)
    finally:
        listener.stop()

    elapsed = time.time() - start_time

    if not stop_event.is_set():
        stop_event.set()
    logcat_thread.join(timeout=3)

    app_result = result_holder[0] if result_holder else None

    test_result = RTATestResult(
        test_id=test_id,
        timestamp=timestamp,
        device_model=device_model,
        device_type=device_type,
        touch_recording=recording,
        app_result=app_result,
        duration_s=elapsed,
    )

    output_path = os.path.join(output_dir, f"{test_id}.json")
    test_result.save(output_path)
    print(f"[RTA Test] Saved: {output_path}")
    print(f"[RTA Test] {test_result.summary()}")

    return test_result


class Mobile:
    """
    Adapter usado pela FSM.

    Responsabilidades:
    - ouvir toque real via adb getevent
    - converter coordenada bruta para pixel da tela
    - devolver (x, y) em pixels
    """

    def __init__(self):
        self.device_name = detect_touchscreen_device()
        self.screen_size = get_screen_size()
        self.x_range, self.y_range = get_touch_axis_ranges(self.device_name)

        self.listener = MobileInputListener(device_filter=self.device_name)
        self.listener.start()

        print(f"[Mobile] Touch device: {self.device_name}")
        print(f"[Mobile] Screen size: {self.screen_size}")
        print(f"[Mobile] X range: {self.x_range}")
        print(f"[Mobile] Y range: {self.y_range}")

    def wait_for_touch_feedback(self, timeout: float = 3) -> Optional[tuple[int, int]]:
        tracker = TouchTracker()
        start = time.time()

        for evt in self.listener.iter_events():
            if time.time() - start > timeout:
                return None

            point = tracker.feed(evt)

            if point and point.action == TouchAction.DOWN:
                touch_px = map_raw_touch_to_screen(
                    raw_x=point.x,
                    raw_y=point.y,
                    x_range=self.x_range,
                    y_range=self.y_range,
                    screen_size=self.screen_size,
                )

                if touch_px is None:
                    return None

                return touch_px

        return None

    def wait_for_touch_with_pressure(
        self, timeout: float = 3, max_pressure_threshold: int = 3000
    ) -> Optional[dict]:
        """
        Espera por toque e retorna dados incluindo pressão e posição.

        Retorna:
            {
                "position": (x, y),
                "pressure": int,
                "duration_sec": float,
                "timestamp": float,
                "excessive_pressure": bool
            }
            ou None se timeout
        """
        tracker = TouchTracker()
        start = time.time()

        for evt in self.listener.iter_events():
            if time.time() - start > timeout:
                return None

            point = tracker.feed(evt)

            if point and point.action == TouchAction.UP:
                touch_px = map_raw_touch_to_screen(
                    raw_x=point.x,
                    raw_y=point.y,
                    x_range=self.x_range,
                    y_range=self.y_range,
                    screen_size=self.screen_size,
                )

                if touch_px is None:
                    return None

                avg_pressure = tracker.avg_pressure
                excessive = avg_pressure > max_pressure_threshold

                return {
                    "position": touch_px,
                    "pressure": int(avg_pressure),
                    "duration_sec": tracker.duration,
                    "timestamp": time.time(),
                    "excessive_pressure": excessive,
                }

        return None

    def monitor_swipe_for_signal_loss(self, timeout: float = 10.0) -> tuple[bool, str]:
        """
        Monitora uma sequência de swipe para detectar perda de sinal ou pressão excessiva.

        Retorna:
            (signal_ok: bool, reason: str)
            - signal_ok=True: swipe completado sem problemas
            - signal_ok=False, reason="signal_loss": dispositivo parou de responder
            - signal_ok=False, reason="excessive_pressure": pressão muito forte
        """
        tracker = TouchTracker()
        start = time.time()
        last_event_time = start
        signal_loss_threshold = 0.5  # segundos sem evento

        try:
            for evt in self.listener.iter_events():
                elapsed = time.time() - start

                if elapsed > timeout:
                    return True, "completed"

                # Verifica se perdeu sinal (nenhum evento por muito tempo)
                current_time = time.time()
                if current_time - last_event_time > signal_loss_threshold:
                    # Há um toque ativo mas nenhum evento por signal_loss_threshold segundos
                    if tracker.total_points > 0 and not tracker.points[-1].action == TouchAction.UP:
                        return False, "signal_loss"

                last_event_time = current_time
                point = tracker.feed(evt)

                # Detecta pressão excessiva
                if point and point.pressure > 3000:
                    return False, "excessive_pressure"

                # Se toque terminou naturalmente, swipe completou
                if point and point.action == TouchAction.UP:
                    return True, "completed"

        except Exception as e:
            return False, f"error:{str(e)}"

        return True, "timeout_ok"

    def stop(self) -> None:
        self.listener.stop()


def main() -> None:
    import sys

    device_type = sys.argv[1] if len(sys.argv) > 1 else "flat"
    print(f"=== RTA Full Test (device_type={device_type}) ===\n")

    result = run_rta_test(
        output_dir="test_results",
        device_type=device_type,
        timeout=120,
    )

    print(f"\n{'=' * 50}")
    print(result.summary())
    if result.app_result:
        print(f"Status: {result.app_result.status}")
        print(f"Accuracy: {result.app_result.accuracy:.1f}%")
    print(f"Device model: {result.device_model}")
    print(f"Touch points recorded: {result.touch_recording.total_points}")
    print(f"File: test_results/{result.test_id}.json")


if __name__ == "__main__":
    main()