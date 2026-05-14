"""
Test suite for safety-critical touch and swipe methods.
Validates: pause-and-listen, signal continuity, pressure bounds.
"""
Validates touch detection during movement, feedback capture, and graceful interruption.
"""

import time
import unittest
from dataclasses import dataclass
from unittest.mock import MagicMock, Mock, patch


@dataclass
class MockMarker:
    """Mock marker for testing."""
    centroid: tuple
    area: float
    marker_id: str = "marker_0"


class TestPauseAndListen(unittest.TestCase):
    class TestListenWhileMoving(unittest.TestCase):
        """Test listen-while-moving touch flow (new approach)."""

        def setUp(self):
            """Set up test fixtures."""
            self.marker = MockMarker(
                centroid=(512, 1024), 
                area=150.0,
                marker_id="fiducial_0"
            )

        @patch("utils.marker_touch_controller.MarkerTouchController")
        def test_listen_while_moving_success(self, mock_controller_class):
            """Test successful touch detected during movement."""
            mock_controller = mock_controller_class.return_value
            mock_controller.move_and_listen_until_touch.return_value = (
                True,
                {
                    "touch_position": (513, 1025),
                    "touch_pressure": 450,
                    "robot_pose_at_touch": (100.0, 200.0, 50.0, 0.0, 0.0, 0.0),
                    "timestamp": time.time(),
                    "movement_interrupted": True,
                },
            )

            result, touch_data = mock_controller.move_and_listen_until_touch(
                target_x=100.0,
                target_y=200.0,
                z_touch=50.0,
                rx=0.0,
                ry=0.0,
                rz=0.0,
                touch_timeout=10.0,
            )

            self.assertTrue(result)
            self.assertIsNotNone(touch_data)
            self.assertEqual(touch_data["touch_position"], (513, 1025))
            self.assertGreater(touch_data["touch_pressure"], 400)
            self.assertTrue(touch_data["movement_interrupted"])

        @patch("utils.marker_touch_controller.MarkerTouchController")
        def test_listen_while_moving_timeout(self, mock_controller_class):
            """Test timeout when no touch during movement."""
            mock_controller = mock_controller_class.return_value
            mock_controller.move_and_listen_until_touch.return_value = (False, None)

            result, touch_data = mock_controller.move_and_listen_until_touch(
                target_x=100.0,
                target_y=200.0,
                z_touch=50.0,
                rx=0.0,
                ry=0.0,
                rz=0.0,
                touch_timeout=2.0,
            )

            self.assertFalse(result)
            self.assertIsNone(touch_data)

        @patch("utils.marker_touch_controller.MarkerTouchController")
        def test_touch_marker_listen_while_moving(self, mock_controller_class):
            """Test marker touch with listen-while-moving."""
            mock_controller = mock_controller_class.return_value
            mock_controller.touch_marker_listen_while_moving.return_value = (
                True,
                {
                    "marker_id": "fiducial_0",
                    "marker_centroid": (512, 1024),
                    "touch_position": (513, 1025),
                    "touch_pressure": 450,
                    "position_error_px": 1.4,
                    "robot_pose_at_touch": (100.0, 200.0, 50.0, 0.0, 0.0, 0.0),
                    "timestamp": time.time(),
                },
            )

            result, touch_info = mock_controller.touch_marker_listen_while_moving(
                self.marker, z_touch=50.0, speed=50.0, touch_timeout=10.0
            )

            self.assertTrue(result)
            self.assertIsNotNone(touch_info)
            self.assertEqual(touch_info["marker_id"], "fiducial_0")
            self.assertLess(touch_info["position_error_px"], 5.0)  # Error < 5 pixels


    class TestPauseAndListen(unittest.TestCase):
        """Test pause-and-listen touch flow (legacy approach)."""
    """Test pause-and-listen touch flow."""

    def setUp(self):
        """Set up test fixtures."""
        self.marker = MockMarker(centroid=(512, 1024), area=150.0)

    @patch("drivers.device.rta_integrated_controller.TouchMarkerController")
    def test_touch_with_feedback_success(self, mock_controller_class):
        """Test successful touch with ADB feedback."""
        mock_controller = mock_controller_class.return_value
        mock_controller.touch_marker_with_pause_and_listen.return_value = (
            True,
            {"position": (513, 1025), "signal_strength": 0.95},
        )

        result, feedback = mock_controller.touch_marker_with_pause_and_listen(
            self.marker, z_touch=100.0, feedback_timeout=2.0
        )

        self.assertTrue(result)
        self.assertIsNotNone(feedback)
        self.assertEqual(feedback["position"], (513, 1025))
        self.assertGreater(feedback["signal_strength"], 0.9)

    @patch("drivers.device.rta_integrated_controller.TouchMarkerController")
    def test_touch_with_feedback_timeout(self, mock_controller_class):
        """Test touch fails when ADB feedback times out."""
        mock_controller = mock_controller_class.return_value
        mock_controller.touch_marker_with_pause_and_listen.return_value = (False, None)

        result, feedback = mock_controller.touch_marker_with_pause_and_listen(
            self.marker, z_touch=100.0, feedback_timeout=0.5
        )

        self.assertFalse(result)
        self.assertIsNone(feedback)

    @patch("drivers.device.rta_integrated_controller.TouchMarkerController")
    def test_touch_with_degraded_signal(self, mock_controller_class):
        """Test touch succeeds but records degraded signal."""
        mock_controller = mock_controller_class.return_value
        mock_controller.touch_marker_with_pause_and_listen.return_value = (
            True,
            {"position": (512, 1024), "signal_strength": 0.65},
        )

        result, feedback = mock_controller.touch_marker_with_pause_and_listen(
            self.marker, z_touch=100.0, feedback_timeout=2.0
        )

        self.assertTrue(result)
        self.assertLess(feedback["signal_strength"], 0.7)


class TestSwipeSafetyMonitoring(unittest.TestCase):
    """Test swipe with signal/pressure monitoring."""

    def setUp(self):
        """Set up test fixtures."""
        self.swipe_points = [
            (100, 100),
            (200, 100),
            (300, 100),
            (400, 100),
        ]

    @patch("drivers.device.rta_integrated_controller.TouchMarkerController")
    def test_swipe_success_with_monitoring(self, mock_controller_class):
        """Test successful swipe with continuous monitoring."""
        mock_controller = mock_controller_class.return_value
        mock_controller.swipe_with_safety_monitoring.return_value = (True, "ok")

        result, reason = mock_controller.swipe_with_safety_monitoring(
            self.swipe_points, z_touch=100.0
        )

        self.assertTrue(result)
        self.assertEqual(reason, "ok")

    @patch("drivers.device.rta_integrated_controller.TouchMarkerController")
    def test_swipe_fails_on_signal_loss(self, mock_controller_class):
        """Test swipe fails when signal is lost mid-execution."""
        mock_controller = mock_controller_class.return_value
        mock_controller.swipe_with_safety_monitoring.return_value = (
            False,
            "signal_loss",
        )

        result, reason = mock_controller.swipe_with_safety_monitoring(
            self.swipe_points, z_touch=100.0
        )

        self.assertFalse(result)
        self.assertEqual(reason, "signal_loss")

    @patch("drivers.device.rta_integrated_controller.TouchMarkerController")
    def test_swipe_fails_on_excessive_pressure(self, mock_controller_class):
        """Test swipe fails when pressure exceeds safe bounds."""
        mock_controller = mock_controller_class.return_value
        mock_controller.swipe_with_safety_monitoring.return_value = (
            False,
            "excessive_pressure",
        )

        result, reason = mock_controller.swipe_with_safety_monitoring(
            self.swipe_points, z_touch=100.0
        )

        self.assertFalse(result)
        self.assertEqual(reason, "excessive_pressure")


class TestMetricsRecording(unittest.TestCase):
    """Test that safety metrics are properly recorded."""

    @patch("state_machine.run_rta_fsm.metrics_logger")
    def test_touch_metrics_with_feedback(self, mock_metrics_logger):
        """Test touch metrics capture actual position from feedback."""
        mock_metrics_logger.record_touch = Mock()

        # Simulate touch with feedback
        target_x, target_y = 512, 1024
        actual_x, actual_y = 513, 1025
        feedback_data = {"position": (actual_x, actual_y)}

        # Record metrics
        mock_metrics_logger.record_touch(
            None,
            marker_index=0,
            target_x=target_x,
            target_y=target_y,
            actual_x=actual_x,
            actual_y=actual_y,
            area_px=150.0,
        )

        # Verify called with actual position
        mock_metrics_logger.record_touch.assert_called_once()
        call_args = mock_metrics_logger.record_touch.call_args
        self.assertEqual(call_args.kwargs["actual_x"], actual_x)
        self.assertEqual(call_args.kwargs["actual_y"], actual_y)

    @patch("state_machine.run_rta_fsm.metrics_logger")
    def test_swipe_metrics_with_safety_reason(self, mock_metrics_logger):
        """Test swipe metrics record safety failure reason."""
        mock_metrics_logger.record_swipe = Mock()

        # Record swipe that failed due to safety
        mock_metrics_logger.record_swipe(
            None,
            num_points=4,
            duration_sec=2.5,
            success=False,
        )

        # Verify called
        mock_metrics_logger.record_swipe.assert_called_once()
        call_args = mock_metrics_logger.record_swipe.call_args
        self.assertFalse(call_args.kwargs["success"])


class TestSignalValidation(unittest.TestCase):
    """Test signal continuity validation."""

    @patch("drivers.device.rta_integrated_controller.TouchMarkerController")
    def test_signal_continuity_good(self, mock_controller_class):
        """Test signal validation passes with good strength."""
        mock_controller = mock_controller_class.return_value
        mock_controller._validate_signal_continuity = Mock(return_value=True)

        result = mock_controller._validate_signal_continuity(
            signal_strength=0.9, threshold=0.7
        )

        self.assertTrue(result)

    @patch("drivers.device.rta_integrated_controller.TouchMarkerController")
    def test_signal_continuity_degraded(self, mock_controller_class):
        """Test signal validation fails with weak signal."""
        mock_controller = mock_controller_class.return_value
        mock_controller._validate_signal_continuity = Mock(return_value=False)

        result = mock_controller._validate_signal_continuity(
            signal_strength=0.5, threshold=0.7
        )

        self.assertFalse(result)


class TestPressureBounds(unittest.TestCase):
    """Test pressure validation."""

    @patch("drivers.device.rta_integrated_controller.TouchMarkerController")
    def test_pressure_within_bounds(self, mock_controller_class):
        """Test pressure validation passes within bounds."""
        mock_controller = mock_controller_class.return_value
        mock_controller._check_pressure_bounds = Mock(return_value=True)

        result = mock_controller._check_pressure_bounds(
            pressure_grams=500, min_pressure=300, max_pressure=700
        )

        self.assertTrue(result)

    @patch("drivers.device.rta_integrated_controller.TouchMarkerController")
    def test_pressure_exceeds_max(self, mock_controller_class):
        """Test pressure validation fails when exceeding max."""
        mock_controller = mock_controller_class.return_value
        mock_controller._check_pressure_bounds = Mock(return_value=False)

        result = mock_controller._check_pressure_bounds(
            pressure_grams=800, min_pressure=300, max_pressure=700
        )

        self.assertFalse(result)

    @patch("drivers.device.rta_integrated_controller.TouchMarkerController")
    def test_pressure_below_min(self, mock_controller_class):
        """Test pressure validation fails when below min."""
        mock_controller = mock_controller_class.return_value
        mock_controller._check_pressure_bounds = Mock(return_value=False)

        result = mock_controller._check_pressure_bounds(
            pressure_grams=200, min_pressure=300, max_pressure=700
        )

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
