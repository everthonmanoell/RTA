"""
Metrics collection and logging for RTA tests.

Tracks:
- Time per state transition
- Touch precision (expected vs actual position)
- Pixel area covered in touches
- Overall test statistics
"""

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class TouchMetric:
    """Record of a single touch event."""

    marker_index: int
    target_x: float
    target_y: float
    actual_x: Optional[float] = None
    actual_y: Optional[float] = None
    area_px: Optional[float] = None
    timestamp: float = field(default_factory=time.time)

    @property
    def precision_mm(self) -> Optional[float]:
        """Calculate precision as distance from expected to actual (pixels to mm estimate)."""
        if self.actual_x is None or self.actual_y is None:
            return None
        dx = self.target_x - self.actual_x
        dy = self.target_y - self.actual_y
        return (dx**2 + dy**2) ** 0.5  # Euclidean distance in pixels


@dataclass
class StateTransitionMetric:
    """Record of a state transition timing."""

    from_state: str
    to_state: str
    duration_sec: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class TestMetrics:
    """Aggregated metrics for a complete test run."""

    test_id: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    state_transitions: List[StateTransitionMetric] = field(default_factory=list)
    touch_events: List[TouchMetric] = field(default_factory=list)
    swipe_events: List[Dict[str, Any]] = field(default_factory=list)
    final_result: Optional[str] = None
    total_steps: int = 0
    error_touches: int = 0

    @property
    def total_duration_sec(self) -> float:
        """Total execution time."""
        end = self.end_time or time.time()
        return end - self.start_time

    @property
    def avg_touch_precision_px(self) -> Optional[float]:
        """Average touch precision across all touches."""
        valid = [t.precision_mm for t in self.touch_events if t.precision_mm is not None]
        return sum(valid) / len(valid) if valid else None

    @property
    def total_area_touched_px(self) -> float:
        """Sum of all pixels touched."""
        return sum(t.area_px or 0 for t in self.touch_events)

    def to_dict(self) -> Dict:
        """Convert to serializable dict."""
        return {
            "test_id": self.test_id,
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
            "end_time": datetime.fromtimestamp(self.end_time).isoformat()
            if self.end_time
            else None,
            "total_duration_sec": self.total_duration_sec,
            "total_steps": self.total_steps,
            "error_touches": self.error_touches,
            "final_result": self.final_result,
            "touch_events": [asdict(t) for t in self.touch_events],
            "state_transitions": [asdict(t) for t in self.state_transitions],
            "swipe_events": self.swipe_events,
            "statistics": {
                "total_area_touched_px": self.total_area_touched_px,
                "avg_touch_precision_px": self.avg_touch_precision_px,
                "num_touches": len(self.touch_events),
                "num_state_transitions": len(self.state_transitions),
            },
        }


class MetricsLogger:
    """Collects and saves test metrics to JSON."""

    def __init__(self, output_dir: Optional[str] = "test_results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)

    def create_test_session(self, test_id: Optional[str] = None) -> TestMetrics:
        """Create a new test session for metrics collection."""
        if test_id is None:
            test_id = datetime.now().strftime("test_%Y%m%d_%H%M%S")
        return TestMetrics(test_id=test_id)

    def record_state_transition(
        self, metrics: TestMetrics, from_state: str, to_state: str, duration_sec: float
    ) -> None:
        """Record a state transition and its duration."""
        transition = StateTransitionMetric(
            from_state=from_state, to_state=to_state, duration_sec=duration_sec
        )
        metrics.state_transitions.append(transition)

    def record_touch(
        self,
        metrics: TestMetrics,
        marker_index: int,
        target_x: float,
        target_y: float,
        actual_x: Optional[float] = None,
        actual_y: Optional[float] = None,
        area_px: Optional[float] = None,
    ) -> None:
        """Record a touch event with position and area."""
        touch = TouchMetric(
            marker_index=marker_index,
            target_x=target_x,
            target_y=target_y,
            actual_x=actual_x,
            actual_y=actual_y,
            area_px=area_px,
        )
        metrics.touch_events.append(touch)

    def record_swipe(
        self,
        metrics: TestMetrics,
        num_points: int,
        duration_sec: float,
        success: bool,
    ) -> None:
        """Record a swipe event."""
        swipe = {
            "num_points": num_points,
            "duration_sec": duration_sec,
            "success": success,
            "timestamp": time.time(),
        }
        metrics.swipe_events.append(swipe)

    def finalize_test(
        self, metrics: TestMetrics, final_result: str, total_steps: int, error_touches: int
    ) -> None:
        """Finalize test metrics."""
        metrics.end_time = time.time()
        metrics.final_result = final_result
        metrics.total_steps = total_steps
        metrics.error_touches = error_touches

    def save_metrics(self, metrics: TestMetrics) -> Path:
        """Save metrics to JSON file."""
        output_file = self.output_dir / f"{metrics.test_id}.json"

        try:
            with open(output_file, "w") as f:
                json.dump(metrics.to_dict(), f, indent=2)
            self.logger.info(f"Metrics saved to {output_file}")
            return output_file
        except Exception as e:
            self.logger.error(f"Failed to save metrics: {e}")
            raise
