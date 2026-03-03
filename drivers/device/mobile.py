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
# Type 0x0003 = EV_ABS (absolute axis)
_EV_ABS = "0003"
# Codes under EV_ABS
_ABS_MT_POSITION_X = "0035"
_ABS_MT_POSITION_Y = "0036"
_ABS_MT_PRESSURE = "003a"
_ABS_MT_TRACKING_ID = "0039"
_ABS_MT_TOUCH_MAJOR = "0030"
_ABS_MT_TOUCH_MINOR = "0031"
# Type 0x0000 = EV_SYN (sync)
_EV_SYN = "0000"
_SYN_REPORT = "0000"
# Type 0x0001 = EV_KEY
_EV_KEY = "0001"
_BTN_TOUCH = "014a"


class TouchAction(Enum):
    """Type of touch action."""
    DOWN = "down"
    MOVE = "move"
    UP = "up"


@dataclass
class TouchPoint:
    """A single touch sample with full coordinates and metadata."""
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
    """Raw event from `adb shell getevent`.

    Typical line format:
    "/dev/input/eventX: TYPE CODE VALUE"
    """

    device: str
    tipo: str
    codigo: str
    valor: str

    @property
    def valor_decimal(self) -> Optional[int]:
        """Converts hex value to int."""
        try:
            return int(self.valor, 16)
        except ValueError:
            return None

    @property
    def valor_signed(self) -> Optional[int]:
        """Converts hex value to signed 32-bit int (for tracking_id = ffffffff → -1)."""
        v = self.valor_decimal
        if v is not None and v >= 0x80000000:
            return v - 0x100000000
        return v

    # --- Axis detection ---

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
        """SYN_REPORT marks the end of one event batch."""
        return self.tipo.lower() == _EV_SYN and self.codigo.lower() == _SYN_REPORT

    @property
    def is_btn_touch(self) -> bool:
        return self.tipo.lower() == _EV_KEY and self.codigo.lower() == _BTN_TOUCH

    @property
    def is_touch_down(self) -> bool:
        """BTN_TOUCH pressed (value=1)."""
        return self.is_btn_touch and self.valor_decimal == 1

    @property
    def is_touch_up(self) -> bool:
        """BTN_TOUCH released (value=0)."""
        return self.is_btn_touch and self.valor_decimal == 0


def start_getevent_process() -> subprocess.Popen:
    """Inicia o processo `adb shell getevent` em modo texto e leitura linha-a-linha."""
    return subprocess.Popen(
        ["adb", "shell", "getevent"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )


def parse_getevent_line(line: str) -> Optional[GetEvent]:
    """Converte uma linha crua do getevent em um objeto `GetEvent`.

    Espera algo como: 
      "/dev/input/event3: 0003 0035 00000abc"
    Retorna None se o formato não bater.
    """
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
    """Itera linhas do stdout até o processo encerrar."""
    assert proc.stdout is not None
    while True:
        line = proc.stdout.readline()
        if not line and proc.poll() is not None:
            break
        if line:
            yield line


def detect_touchscreen_device() -> str:
    """Auto-detects the touchscreen input device via `adb shell getevent -pl`.

    Looks for a device with INPUT_PROP_DIRECT (touchscreen) that has
    ABS_MT_POSITION_X or ABS_X axis. Returns the event name (e.g. 'event9').
    Falls back to 'event9' if detection fails.
    """
    try:
        output = subprocess.check_output(
            ["adb", "shell", "getevent", "-pl"],
            text=True, stderr=subprocess.DEVNULL, timeout=5,
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
    return "event9"  # fallback


class MobileInputListener:
    """Listener for raw events from `adb shell getevent`.

    - `device_filter`: filters by device path. Use None to auto-detect touchscreen.
    - Main methods: `start()`, `stop()`, `iter_events()`, `run_loop()`.
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
        """Runs a loop calling `on_event` for each filtered event."""
        try:
            for evt in self.iter_events():
                on_event(evt)
        finally:
            self.stop()


# ==========================================
# TOUCH TRACKER: Accumulates raw events into TouchPoints
# ==========================================

class TouchTracker:
    """Converts raw GetEvent stream into high-level TouchPoint objects.

    Accumulates X, Y, pressure, etc. between SYN_REPORT events.
    Emits a TouchPoint with the correct action (DOWN, MOVE, UP) on each sync.

    Usage:
        tracker = TouchTracker()
        for evt in listener.iter_events():
            point = tracker.feed(evt)
            if point:
                print(f"{point.action.value}: ({point.x}, {point.y}) P={point.pressure}")
    """

    def __init__(self) -> None:
        self._x: int = 0
        self._y: int = 0
        self._pressure: int = 0
        self._touch_major: int = 0
        self._touch_minor: int = 0
        self._tracking_id: int = -1
        self._finger_down: bool = False
        self._dirty: bool = False  # True if any axis changed since last sync

    def feed(self, evt: GetEvent) -> Optional[TouchPoint]:
        """Feed a raw event. Returns a TouchPoint on SYN_REPORT, or None."""
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
            # Determine action
            if not self._finger_down or self._tracking_id == -1:
                action = TouchAction.UP
            elif not hasattr(self, "_was_down") or not self._was_down:
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


# ==========================================
# TOUCH RECORDER: Records all TouchPoints for metrics
# ==========================================

@dataclass
class TouchRecording:
    """A complete recording of touch events with computed metrics."""
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
        """Total recording duration in seconds."""
        if len(self.points) < 2:
            return 0.0
        return self.points[-1].timestamp - self.points[0].timestamp

    @property
    def x_range(self) -> tuple[int, int]:
        """(min_x, max_x) across all points."""
        xs = [p.x for p in self.points if p.action != TouchAction.UP]
        return (min(xs), max(xs)) if xs else (0, 0)

    @property
    def y_range(self) -> tuple[int, int]:
        """(min_y, max_y) across all points."""
        ys = [p.y for p in self.points if p.action != TouchAction.UP]
        return (min(ys), max(ys)) if ys else (0, 0)

    @property
    def avg_pressure(self) -> float:
        """Average pressure across move/down points."""
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
        """Save recording to a JSON file."""
        with open(path, "w") as f:
            f.write(self.to_json())


def record_touch(
    listener: MobileInputListener,
    timeout: float = 30.0,
    stop_on_up: bool = True,
) -> TouchRecording:
    """Records touch events into a TouchRecording.

    Args:
        listener: MobileInputListener instance (will be started if not already).
        timeout: Max recording time in seconds.
        stop_on_up: If True, stops after the first complete touch (DOWN→MOVE→UP).

    Returns:
        TouchRecording with all captured points.

    Usage:
        listener = MobileInputListener(device_filter="event3")
        recording = record_touch(listener, timeout=10)
        print(f"Captured {recording.total_points} points in {recording.duration:.2f}s")
        print(f"X range: {recording.x_range}, Y range: {recording.y_range}")
        print(f"Avg pressure: {recording.avg_pressure:.0f}")
        recording.save("touch_data.json")
    """
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


# ==========================================
# RTA RESULT: Read grid validation result via logcat
# ==========================================

@dataclass(frozen=True)
class RTAResult:
    """Result from the RTA app grid validation."""

    status: str          # "success" or "fail"
    hits: int            # Number of border cells correctly painted
    total: int           # Total border cells expected
    errors: int          # Number of internal cells touched
    reason: str          # Error message (empty on success)
    device_type: str     # Device profile used

    @property
    def is_success(self) -> bool:
        return self.status == "success"

    @property
    def accuracy(self) -> float:
        """Border painting accuracy as a percentage (0-100)."""
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
    """Background thread that listens for RTA_RESULT via logcat."""
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
                    result_holder.append(RTAResult(
                        status=data.get("status", "unknown"),
                        hits=data.get("hits", 0),
                        total=data.get("total", 0),
                        errors=data.get("errors", 0),
                        reason=data.get("reason", ""),
                        device_type=data.get("device_type", ""),
                    ))
                    stop_event.set()
                    return
                except json.JSONDecodeError:
                    continue
    finally:
        proc.terminate()
        proc.wait()


def wait_for_rta_result(timeout: float = 120.0) -> Optional[RTAResult]:
    """Waits for the RTA app to emit a result via logcat.

    Clears the logcat buffer first, then listens for the RTA_RESULT tag.
    Returns an RTAResult when one is received, or None on timeout.
    """
    subprocess.run(["adb", "logcat", "-c"], capture_output=True)

    result_holder: list[RTAResult] = []
    stop = threading.Event()
    _listen_for_rta_result(result_holder, stop, timeout)
    return result_holder[0] if result_holder else None


# ==========================================
# RTA TEST: Full test session (touch + result)
# ==========================================

def get_device_model() -> str:
    """Gets the phone model via ADB (e.g. 'motorola edge 50 fusion')."""
    try:
        brand = subprocess.check_output(
            ["adb", "shell", "getprop", "ro.product.brand"],
            text=True, stderr=subprocess.DEVNULL, timeout=5,
        ).strip()
        model = subprocess.check_output(
            ["adb", "shell", "getprop", "ro.product.model"],
            text=True, stderr=subprocess.DEVNULL, timeout=5,
        ).strip()
        # Avoid duplication like "motorola motorola edge 50 fusion"
        if brand and model.lower().startswith(brand.lower()):
            return model
        return f"{brand} {model}" if brand else model
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        return "unknown"


@dataclass
class RTATestResult:
    """Complete RTA test result: touch recording + app validation result."""
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
        """Save full test result to a JSON file."""
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
    """Runs a complete RTA test: listens for touch + waits for app result.

    This function:
    1. Clears the logcat buffer
    2. Starts the RTA app on the phone via ADB
    3. Records ALL touch events during the entire test
    4. Waits for the app to emit a result (success/fail) via logcat
    5. Stops recording and saves everything to a JSON file

    Args:
        output_dir: Directory to save test JSON files.
        device_type: Device profile to use ("flat", "foldable", "one", etc.)
        device_model: Phone model name for metrics (auto-detected if None).
        timeout: Max test duration in seconds.
        test_id: Optional custom test ID. Defaults to timestamp-based.

    Returns:
        RTATestResult with all data.

    Usage:
        result = run_rta_test(device_type="flat", timeout=60)
        result = run_rta_test(device_type="flat", device_model="motorola edge 40")
        print(result.summary())
        # JSON saved automatically to test_results/test_20260303_143025.json
    """
    now = datetime.now()
    if test_id is None:
        test_id = f"test_{now.strftime('%Y%m%d_%H%M%S')}"
    timestamp = now.isoformat()

    # Auto-detect phone model if not provided
    if device_model is None:
        device_model = get_device_model()

    print(f"[RTA Test] Starting test: {test_id}")
    print(f"[RTA Test] Device model: {device_model}")
    print(f"[RTA Test] Device type: {device_type}")

    # 1. Clear logcat
    subprocess.run(["adb", "logcat", "-c"], capture_output=True)

    # 2. Start listening for app result in background thread
    result_holder: list[RTAResult] = []
    stop_event = threading.Event()
    logcat_thread = threading.Thread(
        target=_listen_for_rta_result,
        args=(result_holder, stop_event, timeout),
        daemon=True,
    )
    logcat_thread.start()

    # 3. Launch the RTA app
    subprocess.run([
        "adb", "shell", "am", "start", "-n",
        "com.example.rta/.MainActivity",
        "--es", "device_type", device_type,
    ], capture_output=True)
    print("[RTA Test] App launched. Recording touches...")

    # 4. Record touch events until app emits result or timeout
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

    # 5. Wait for logcat thread to finish (short grace period)
    if not stop_event.is_set():
        stop_event.set()
    logcat_thread.join(timeout=3)

    app_result = result_holder[0] if result_holder else None

    # 6. Build test result
    test_result = RTATestResult(
        test_id=test_id,
        timestamp=timestamp,
        device_model=device_model,
        device_type=device_type,
        touch_recording=recording,
        app_result=app_result,
        duration_s=elapsed,
    )

    # 7. Save to JSON
    output_path = os.path.join(output_dir, f"{test_id}.json")
    test_result.save(output_path)
    print(f"[RTA Test] Saved: {output_path}")
    print(f"[RTA Test] {test_result.summary()}")

    return test_result


# Standalone execution
def main() -> None:
    import sys

    device_type = sys.argv[1] if len(sys.argv) > 1 else "flat"
    print(f"=== RTA Full Test (device_type={device_type}) ===\n")

    result = run_rta_test(
        output_dir="test_results",
        device_type=device_type,
        timeout=120,
    )

    print(f"\n{'='*50}")
    print(result.summary())
    if result.app_result:
        print(f"Status: {result.app_result.status}")
        print(f"Accuracy: {result.app_result.accuracy:.1f}%")
    print(f"Device model: {result.device_model}")
    print(f"Touch points recorded: {result.touch_recording.total_points}")
    print(f"File: test_results/{result.test_id}.json")


if __name__ == "__main__":
    main()