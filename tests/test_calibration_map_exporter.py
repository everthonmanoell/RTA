import json
import sys
import tempfile
import types
from dataclasses import dataclass
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch


if "numpy" not in sys.modules:
    numpy_stub = types.ModuleType("numpy")
    numpy_stub.ndarray = object
    numpy_stub.floating = float
    numpy_stub.integer = int
    sys.modules["numpy"] = numpy_stub

if "scipy" not in sys.modules:
    scipy_stub = types.ModuleType("scipy")
    interpolate_stub = types.ModuleType("scipy.interpolate")
    interpolate_stub.griddata = lambda *args, **kwargs: None
    scipy_stub.interpolate = interpolate_stub
    sys.modules["scipy"] = scipy_stub
    sys.modules["scipy.interpolate"] = interpolate_stub

if "aether_rdk" not in sys.modules:
    aether_stub = types.ModuleType("aether_rdk")
    datatypes_stub = types.ModuleType("aether_rdk.datatypes")

    class Pose:
        pass

    datatypes_stub.Pose = Pose
    aether_stub.datatypes = datatypes_stub
    sys.modules["aether_rdk"] = aether_stub
    sys.modules["aether_rdk.datatypes"] = datatypes_stub

from utils.calibration_map_exporter import CalibrationMapExporter


@dataclass
class DummyPose:
    x: float = 1.234
    y: float = 5.678
    z: float = 9.101


@dataclass
class DummyMarker:
    marker_id: int
    centroid: tuple


@dataclass
class DummySafePose:
    rx: float = 0.0
    ry: float = 1.0
    rz: float = 2.0
    fig: int = 3


class CalibrationMapExporterTests(TestCase):
    def setUp(self):
        self.marker_infos = [DummyMarker(marker_id=1, centroid=(10, 20))]
        self.touch_poses_dict = {1: DummyPose()}
        self.safe_pose = DummySafePose()

    @patch("utils.calibration_map_exporter.interpolate_robot_pose", return_value=(1.0, 2.0, 3.0))
    @patch("utils.calibration_map_exporter.time.strftime", return_value="20260506_120000")
    @patch("utils.calibration_map_exporter.time.time", return_value=1778068800.0)
    def test_export_separates_by_device_model(self, *_mocked_time):
        with tempfile.TemporaryDirectory() as tmp_dir:
            ok = CalibrationMapExporter.export(
                output_dir=tmp_dir,
                device_type="flat",
                device_model="Samsung Galaxy S24 / Ultra",
                useful_rect_px=(0, 0, 100, 200),
                centroid_rect_px=(50, 100),
                marker_infos=self.marker_infos,
                touch_poses_dict=self.touch_poses_dict,
                safe_pose=self.safe_pose,
                dir_separation=True,
            )

            self.assertTrue(ok)

            output_path = Path(tmp_dir) / "Samsung_Galaxy_S24_Ultra"
            files = list(output_path.glob("physical_calibration_map_20260506_120000_1778068800.json"))
            self.assertEqual(len(files), 1)

            payload = json.loads(files[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["device_type"], "flat")
            self.assertEqual(payload["markers"][0]["marker_id"], 1)

    @patch("utils.calibration_map_exporter.interpolate_robot_pose", return_value=(1.0, 2.0, 3.0))
    @patch("utils.calibration_map_exporter.time.strftime", return_value="20260506_120001")
    @patch("utils.calibration_map_exporter.time.time", return_value=1778068801.0)
    def test_export_keeps_flat_output_when_not_separating(self, *_mocked_time):
        with tempfile.TemporaryDirectory() as tmp_dir:
            ok = CalibrationMapExporter.export(
                output_dir=tmp_dir,
                device_type="flat",
                device_model="Pixel 8",
                useful_rect_px=(0, 0, 100, 200),
                centroid_rect_px=(50, 100),
                marker_infos=self.marker_infos,
                touch_poses_dict=self.touch_poses_dict,
                safe_pose=self.safe_pose,
                dir_separation=False,
            )

            self.assertTrue(ok)
            files = list(Path(tmp_dir).glob("physical_calibration_map_20260506_120001_1778068801.json"))
            self.assertEqual(len(files), 1)