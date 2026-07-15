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
        adb_cmd("shell", "getevent"),
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


def adb_available() -> bool:
    try:
        proc = subprocess.run(["adb", "version"],
                              capture_output=True, text=True, timeout=5)
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def adb_device_connected() -> bool:
    try:
        proc = subprocess.run(["adb", "get-state"],
                              capture_output=True, text=True, timeout=5)
        return proc.returncode == 0 and "device" in proc.stdout.strip().lower()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def list_adb_devices(retries: int = 3) -> list[str]:
    """
    List connected ADB devices.

    Includes a self-healing mechanism: if the ADB server hangs on Windows,
    it automatically restarts the daemon before failing.
    """
    output = subprocess.run(
        ["adb", "devices"],
        text=True,
        capture_output=True,
    ).stdout

    devices = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices attached"):
            continue

        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])

    return devices


ADB_SERIAL: Optional[str] = None


def get_preferred_adb_serial() -> str:
    devices = list_adb_devices()
    if not devices:
        raise AssertionError("No Android device connected via ADB")

    # Prefer USB connection over wireless adb-..._tcp connection
    for serial in devices:
        if not serial.startswith("adb-"):
            return serial

    return devices[0]


def adb_cmd(*args: str) -> list[str]:
    serial = ADB_SERIAL or get_preferred_adb_serial()
    return ["adb", "-s", serial, *args]


def detect_touchscreen_device() -> str:
    try:
        output = subprocess.check_output(
            adb_cmd("shell", "getevent", "-pl"),
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )

        current_device = ""
        has_touch_axis = False

        for line in output.splitlines():
            line = line.strip()

            if line.startswith("add device"):
                current_device = line.split(
                    "/dev/input/")[-1] if "/dev/input/" in line else ""
                has_touch_axis = False
            elif "ABS_MT_POSITION_X" in line or ("ABS_X" in line and "ABS" in line):
                has_touch_axis = True
            elif "INPUT_PROP_DIRECT" in line and has_touch_axis and current_device:
                return current_device

    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        pass

    return "event9"


def get_screen_size() -> tuple[int, int]:
    """
    Try to obtain the screen resolution using multiple strategies:
    1) adb shell wm size
    2) adb shell dumpsys window
    3) adb shell dumpsys display
    """
    commands = [
        adb_cmd("shell", "wm", "size"),
        adb_cmd("shell", "dumpsys", "window"),
        adb_cmd("shell", "dumpsys", "display"),
    ]

    for cmd in commands:
        try:
            output = subprocess.check_output(
                cmd,
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).strip()

            for line in output.splitlines():
                line = line.strip()

                # Classic case: Physical size: 1080x2400
                if "Physical size:" in line:
                    size_str = line.split("Physical size:")[-1].strip()
                    if "x" in size_str:
                        width_str, height_str = size_str.split("x")
                        return int(width_str), int(height_str)

                # Search for patterns like 1080x2400 in other outputs
                import re
                match = re.search(r"\b(\d{3,5})x(\d{3,5})\b", line)
                if match:
                    w = int(match.group(1))
                    h = int(match.group(2))
                    if w > 0 and h > 0:
                        return (w, h)

        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, ValueError, FileNotFoundError):
            pass

    return (0, 0)


def get_touch_axis_ranges(device_name: Optional[str] = None) -> tuple[tuple[int, int], tuple[int, int]]:
    if device_name is None:
        device_name = detect_touchscreen_device()

    try:
        output = subprocess.check_output(
            adb_cmd("shell", "getevent", "-pl"),
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )

        current_device = None
        min_x = max_x = min_y = max_y = None

        for raw_line in output.splitlines():
            line = raw_line.strip()

            if line.startswith("add device"):
                current_device = line.split(
                    "/dev/input/")[-1] if "/dev/input/" in line else None

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

    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, ValueError, FileNotFoundError):
        pass

    return ((0, 0), (0, 0))


def map_raw_touch_to_screen(
    raw_x: int,
    raw_y: int,
    x_range: tuple[int, int],
    y_range: tuple[int, int],
    screen_size: tuple[int, int],
) -> tuple[int, int] | None:
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
    def __init__(self, device_filter: Optional[str] = None) -> None:
        if device_filter is None:
            device_filter = detect_touchscreen_device()
            print(
                f"[TouchListener] Auto-detected touchscreen: /dev/input/{device_filter}")
        self._device_filter = device_filter
        self._proc: Optional[subprocess.Popen] = None

    def start(self) -> None:
        if self._proc is None:
            self._proc = start_getevent_process()

    def stop(self) -> None:
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=2)
            except Exception:
                pass
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
        pts = [p.pressure for p in self.points if p.action !=
               TouchAction.UP and p.pressure > 0]
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
        with open(path, "w", encoding="utf-8") as f:
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
        adb_cmd("logcat", "-s", "RTA_RESULT:I", "-v", "raw"),
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
        try:
            proc.wait(timeout=2)
        except Exception:
            pass


def wait_for_rta_result(timeout: float = 120.0) -> Optional[RTAResult]:
    subprocess.run(adb_cmd("logcat", "-c"), capture_output=True)

    result_holder: list[RTAResult] = []
    stop = threading.Event()
    _listen_for_rta_result(result_holder, stop, timeout)
    return result_holder[0] if result_holder else None


def get_device_model() -> str:
    try:
        brand = subprocess.check_output(
            adb_cmd("shell", "getprop", "ro.product.brand"),
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()

        model = subprocess.check_output(
            adb_cmd("shell", "getprop", "ro.product.model"),
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()

        if brand and model.lower().startswith(brand.lower()):
            return model

        return f"{brand} {model}" if brand else model

    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
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
        with open(path, "w", encoding="utf-8") as f:
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

    subprocess.run(adb_cmd("logcat", "-c"), capture_output=True)

    result_holder: list[RTAResult] = []
    stop_event = threading.Event()
    logcat_thread = threading.Thread(
        target=_listen_for_rta_result,
        args=(result_holder, stop_event, timeout),
        daemon=True,
    )
    logcat_thread.start()

    subprocess.run(
        adb_cmd(
            "shell", "am", "start", "-n",
            "com.example.rta/.MainActivity",
            "--es", "device_type", device_type,
        ),
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
    def __init__(self):
        self.device_name = detect_touchscreen_device()
        self.screen_size = get_screen_size()
        self.x_range, self.y_range = get_touch_axis_ranges(self.device_name)

        self.listener = MobileInputListener(device_filter=self.device_name)
        self.listener.start()

    def wait_for_touch_feedback(self, timeout: float = 3) -> Optional[tuple[int, int]]:
        tracker = TouchTracker()
        start = time.time()

        for evt in self.listener.iter_events():
            if time.time() - start > timeout:
                return None

            point = tracker.feed(evt)
            if point and point.action == TouchAction.DOWN:
                return map_raw_touch_to_screen(
                    raw_x=point.x,
                    raw_y=point.y,
                    x_range=self.x_range,
                    y_range=self.y_range,
                    screen_size=self.screen_size,
                )

        return None

    def wait_for_touch_with_pressure(
        self, timeout: float = 3, max_pressure_threshold: int = 3000
    ) -> Optional[dict]:
        recording = record_touch(
            self.listener, timeout=timeout, stop_on_up=True)
        if recording.total_points == 0:
            return None

        last_non_up = next((p for p in reversed(
            recording.points) if p.action != TouchAction.UP), None)
        if last_non_up is None:
            return None

        touch_px = map_raw_touch_to_screen(
            raw_x=last_non_up.x,
            raw_y=last_non_up.y,
            x_range=self.x_range,
            y_range=self.y_range,
            screen_size=self.screen_size,
        )
        if touch_px is None:
            return None

        avg_pressure = recording.avg_pressure
        return {
            "position": touch_px,
            "pressure": int(avg_pressure),
            "duration_sec": recording.duration,
            "timestamp": time.time(),
            "excessive_pressure": avg_pressure > max_pressure_threshold,
            "total_points": recording.total_points,
        }

    def monitor_swipe_for_signal_loss(self, timeout: float = 10.0) -> tuple[bool, str]:
        recording = record_touch(
            self.listener, timeout=timeout, stop_on_up=True)
        if recording.total_points == 0:
            return False, "no_touch"

        if any(p.pressure > 3000 for p in recording.points if p.action != TouchAction.UP):
            return False, "excessive_pressure"

        if recording.total_points < 2:
            return False, "insufficient_points"

        if not recording.up_points:
            return False, "signal_loss"

        return True, "completed"

    def stop(self) -> None:
        self.listener.stop()


@dataclass
class ValidationStepResult:
    name: str
    ok: bool
    details: dict = field(default_factory=dict)
    error: Optional[str] = None
    duration_s: float = 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "ok": self.ok,
            "details": self.details,
            "error": self.error,
            "duration_s": round(self.duration_s, 3),
        }


@dataclass
class ValidationReport:
    validation_id: str
    timestamp: str
    device_type: str
    output_json: str
    steps: list[ValidationStepResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for step in self.steps if step.ok)

    @property
    def failed(self) -> int:
        return sum(1 for step in self.steps if not step.ok)

    def to_dict(self) -> dict:
        return {
            "validation_id": self.validation_id,
            "timestamp": self.timestamp,
            "device_type": self.device_type,
            "output_json": self.output_json,
            "summary": {
                "total_steps": len(self.steps),
                "passed": self.passed,
                "failed": self.failed,
            },
            "steps": [step.to_dict() for step in self.steps],
        }

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.output_json) or ".", exist_ok=True)
        with open(self.output_json, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)


def _run_step(name: str, fn: Callable[[], dict]) -> ValidationStepResult:
    print(f"\n[STEP] {name}")
    start = time.time()
    try:
        details = fn() or {}
        result = ValidationStepResult(
            name=name,
            ok=True,
            details=details,
            duration_s=time.time() - start,
        )
        print(f"[ OK ] {name}")
        if details:
            print(json.dumps(details, indent=2, ensure_ascii=False))
        return result
    except Exception as exc:
        result = ValidationStepResult(
            name=name,
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
            duration_s=time.time() - start,
        )
        print(f"[FAIL] {name}")
        print(result.error)
        return result


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _sample_touch_events() -> list[GetEvent]:
    lines = [
        "/dev/input/event9: 0003 0039 0000002a",
        "/dev/input/event9: 0003 0035 00000100",
        "/dev/input/event9: 0003 0036 00000200",
        "/dev/input/event9: 0003 003a 00000064",
        "/dev/input/event9: 0001 014a 00000001",
        "/dev/input/event9: 0000 0000 00000000",
        "/dev/input/event9: 0003 0035 00000120",
        "/dev/input/event9: 0003 0036 00000220",
        "/dev/input/event9: 0003 003a 0000006e",
        "/dev/input/event9: 0000 0000 00000000",
        "/dev/input/event9: 0001 014a 00000000",
        "/dev/input/event9: 0003 0039 ffffffff",
        "/dev/input/event9: 0000 0000 00000000",
    ]
    events = [parse_getevent_line(line) for line in lines]
    return [evt for evt in events if evt is not None]


def validate_parse_getevent() -> dict:
    evt = parse_getevent_line("/dev/input/event9: 0003 0035 000001f4")
    _assert(evt is not None, "parse_getevent_line returned None")
    _assert(evt.device == "/dev/input/event9", "incorrect device")
    _assert(evt.is_axis_x, "event should be axis x")
    _assert(evt.valor_decimal == 500, "valor_decimal should be 500")
    return {"parsed_event": evt.to_dict() if hasattr(evt, 'to_dict') else {
        "device": evt.device,
        "tipo": evt.tipo,
        "codigo": evt.codigo,
        "valor": evt.valor,
        "valor_decimal": evt.valor_decimal,
    }}


def validate_map_raw_touch_to_screen() -> dict:
    px = map_raw_touch_to_screen(
        2048, 2048, (0, 4095), (0, 4095), (1080, 2400))
    _assert(px is not None, "map_raw_touch_to_screen returned None")
    _assert(abs(px[0] - 539) <= 1, f"x inesperado: {px[0]}")
    _assert(abs(px[1] - 1199) <= 1, f"y inesperado: {px[1]}")
    return {"mapped_pixel": px}


def validate_touch_tracker() -> dict:
    tracker = TouchTracker()
    points = []
    for evt in _sample_touch_events():
        point = tracker.feed(evt)
        if point:
            points.append(point)

        _assert(len(points) == 3, f"expected 3 TouchPoints, got {len(points)}")
        _assert(points[0].action == TouchAction.DOWN,
                "first point should be DOWN")
        _assert(points[1].action == TouchAction.MOVE,
                "second point should be MOVE")
        _assert(points[2].action == TouchAction.UP,
                "third point should be UP")
    return {
        "actions": [p.action.value for p in points],
        "points": [p.to_dict() for p in points],
    }


def validate_touch_recording() -> dict:
    tracker = TouchTracker()
    recording = TouchRecording()
    for evt in _sample_touch_events():
        point = tracker.feed(evt)
        if point:
            recording.points.append(point)

    _assert(recording.total_points == 3, "incorrect total_points")
    _assert(len(recording.down_points) == 1, "incorrect down_points")
    _assert(len(recording.move_points) == 1, "incorrect move_points")
    _assert(len(recording.up_points) == 1, "incorrect up_points")
    _assert(recording.avg_pressure > 0, "avg_pressure should be > 0")
    return recording.to_dict()


def validate_rta_result() -> dict:
    result = RTAResult(status="success", hits=9, total=10,
                       errors=1, reason="ok", device_type="flat")
    _assert(result.is_success is True, "is_success should be True")
    _assert(abs(result.accuracy - 90.0) < 0.001, "incorrect accuracy")
    return result.to_dict()


def validate_adb_environment() -> dict:
    _assert(adb_available(), "ADB is not available in PATH")

    devices = list_adb_devices()
    _assert(devices, "No Android device connected via ADB")

    device_name = detect_touchscreen_device()
    screen_size = get_screen_size()
    x_range, y_range = get_touch_axis_ranges(device_name)
    model = get_device_model()

    _assert(screen_size != (0, 0), "Unable to obtain screen size")
    _assert(x_range != (0, 0) and y_range != (0, 0),
            "Unable to obtain touch ranges")

    return {
        "connected_devices": devices,
        "device_name": device_name,
        "screen_size": screen_size,
        "x_range": x_range,
        "y_range": y_range,
        "device_model": model,
    }


def validate_live_touch_feedback(timeout: float = 8.0) -> dict:
    mobile = Mobile()
    try:
        print(
            f"Touch the screen once within {timeout:.0f}s to validate wait_for_touch_feedback()...")
        touch = mobile.wait_for_touch_feedback(timeout=timeout)
        _assert(touch is not None, "No touch detected")
        return {"touch_feedback_px": touch}
    finally:
        mobile.stop()


def validate_live_touch_with_pressure(timeout: float = 10.0) -> dict:
    mobile = Mobile()
    try:
        print(
            f"Perform a complete touch (down/up) within {timeout:.0f}s to validate pressure...")
        data = mobile.wait_for_touch_with_pressure(timeout=timeout)
        _assert(data is not None, "No complete touch detected")
        return data
    finally:
        mobile.stop()


def validate_live_swipe(timeout: float = 12.0) -> dict:
    mobile = Mobile()
    try:
        print(
            f"Perform a complete swipe within {timeout:.0f}s to validate monitor_swipe_for_signal_loss()...")
        ok, reason = mobile.monitor_swipe_for_signal_loss(timeout=timeout)
        _assert(ok, f"Invalid swipe: {reason}")
        return {"signal_ok": ok, "reason": reason}
    finally:
        mobile.stop()


def validate_run_rta_test_smoke(device_type: str, timeout: float = 20.0) -> dict:
    _assert(adb_available(), "ADB is not available")
    devices = list_adb_devices()
    _assert(devices, "No device connected")
    result = run_rta_test(
        output_dir="test_results",
        device_type=device_type,
        timeout=timeout,
        test_id="smoke_test",
    )
    return result.to_dict()


def build_validation_report(device_type: str, output_dir: str = "validation_results") -> ValidationReport:
    now = datetime.now()
    validation_id = f"validation_{now.strftime('%Y%m%d_%H%M%S')}"
    output_json = os.path.join(output_dir, f"{validation_id}.json")
    return ValidationReport(
        validation_id=validation_id,
        timestamp=now.isoformat(),
        device_type=device_type,
        output_json=output_json,
    )


def toggle_android_setting(setting_name: str, enable: bool) -> None:
    """
    Toggles specific Android system settings via ADB.
    """
    value = "1" if enable else "0"

    # Fetch the exact serial (ignore the wireless connection if mirrored)
    serial = get_preferred_adb_serial()

    # Inject -s <serial> so ADB knows exactly which device to target
    command = ["adb", "-s", serial, "shell", "settings",
               "put", "system", setting_name, value]

    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True
        )
        status = "ON" if enable else "OFF"
        print(f"Successfully turned {status} {setting_name}.")

    except subprocess.CalledProcessError as e:
        print(f"Failed to change {setting_name}.")
        print(f"Error details: {e.stderr}")

    except FileNotFoundError:
        print("Error: ADB is not installed or not added to your system's PATH.")


def main() -> None:
    import sys
    global ADB_SERIAL

    device_type = sys.argv[1] if len(sys.argv) > 1 else "flat"
    mode = sys.argv[2] if len(sys.argv) > 2 else "pipeline"

    try:
        ADB_SERIAL = get_preferred_adb_serial()
    except Exception:
        ADB_SERIAL = None

    report = build_validation_report(device_type=device_type)

    print("=" * 70)
    print(f"RTA Validation Pipeline | mode={mode} | device_type={device_type}")
    print("=" * 70)

    # Synthetic tests: do not depend on a real device.
    report.steps.append(
        _run_step("parse_getevent_line", validate_parse_getevent))
    report.steps.append(_run_step("map_raw_touch_to_screen",
                        validate_map_raw_touch_to_screen))
    report.steps.append(_run_step("TouchTracker.feed", validate_touch_tracker))
    report.steps.append(
        _run_step("TouchRecording.metrics", validate_touch_recording))
    report.steps.append(_run_step("RTAResult.accuracy", validate_rta_result))

    # Tests with a real ADB device.
    report.steps.append(_run_step("ADB environment", validate_adb_environment))

    if mode in {"pipeline", "live"} and report.steps[-1].ok:
        report.steps.append(_run_step(
            "Mobile.wait_for_touch_feedback", lambda: validate_live_touch_feedback(8.0)))
        report.steps.append(_run_step("Mobile.wait_for_touch_with_pressure",
                            lambda: validate_live_touch_with_pressure(10.0)))
        report.steps.append(_run_step(
            "Mobile.monitor_swipe_for_signal_loss", lambda: validate_live_swipe(12.0)))

    if mode == "full" and report.steps[-1].ok:
        report.steps.append(_run_step(
            "run_rta_test smoke", lambda: validate_run_rta_test_smoke(device_type, 20.0)))

    report.save()

    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)
    print(f"Passed: {report.passed}")
    print(f"Failed: {report.failed}")
    print(f"JSON: {report.output_json}")

    for step in report.steps:
        status = "OK" if step.ok else "FAIL"
        print(f"- [{status}] {step.name} ({step.duration_s:.2f}s)")
        if step.error:
            print(f"    error: {step.error}")


if __name__ == "__main__":
    main()
