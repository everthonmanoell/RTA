import time
import json
import logging
import re
from enum import Enum, auto
from pathlib import Path
from utils.coordinate_transform import interpolate_robot_pose

class CalibrationMapExporter:

    @staticmethod
    def _sanitize_path_segment(value: str) -> str:
        cleaned = re.sub(r'[<>:"/\\|?*\s]+', "_", str(value).strip())
        cleaned = cleaned.strip("._")
        return cleaned or "unknown"

    @staticmethod
    def _resolve_output_path(output_dir: str, device_type: str, device_model: str, dir_separation: bool) -> Path:
        out_path = Path(output_dir)
        if not dir_separation:
            return out_path

        folder_name = CalibrationMapExporter._sanitize_path_segment(device_model or device_type)
        return out_path / folder_name

    @staticmethod
    def export(
        output_dir: str,
        device_type: str,
        useful_rect_px: tuple,
        centroid_rect_px: tuple,
        marker_infos: list,
        touch_poses_dict: dict,
        safe_pose,
        device_touch_interaction: dict = None,
        execution_duration_s: float = None,
        calibration_succeed: bool = None,
        device_model: str = None,
        dir_separation: bool = False,
    ) -> bool:
        """Gera e salva o JSON do mapa de calibração físico."""
        logging.info("Gerando mapa de calibração universal (Pixel -> Físico)...")
        
        physical_corners = {}
        if useful_rect_px is not None:
            u_x_min, u_y_min, u_x_max, u_y_max = useful_rect_px
            
            # Converte Quinas
            tl_x, tl_y, tl_z = interpolate_robot_pose(u_x_min, u_y_min, centroid_rect_px, touch_poses_dict, marker_infos)
            tr_x, tr_y, tr_z = interpolate_robot_pose(u_x_max, u_y_min, centroid_rect_px, touch_poses_dict, marker_infos)
            bl_x, bl_y, bl_z = interpolate_robot_pose(u_x_min, u_y_max, centroid_rect_px, touch_poses_dict, marker_infos)
            br_x, br_y, br_z = interpolate_robot_pose(u_x_max, u_y_max, centroid_rect_px, touch_poses_dict, marker_infos)
            
            physical_corners = {
                "top_left": {"x": round(tl_x, 2), "y": round(tl_y, 2), "z": round(tl_z, 2)},
                "top_right": {"x": round(tr_x, 2), "y": round(tr_y, 2), "z": round(tr_z, 2)},
                "bottom_left": {"x": round(bl_x, 2), "y": round(bl_y, 2), "z": round(bl_z, 2)},
                "bottom_right": {"x": round(br_x, 2), "y": round(br_y, 2), "z": round(br_z, 2)}
            }

        # Estrutura JSON
        calibration_map = {
            "timestamp_epoch_s": time.time(),
            "device_type": device_type,
            "calibration_mode": "bilinear_physical_touches",
            "execution_duration_s": round(float(execution_duration_s), 3) if execution_duration_s is not None else None,
            "calibration_succeed": bool(calibration_succeed),
            "physical_screen_corners_mm": physical_corners,
            "safe_orientation": {
                "rx": float(safe_pose.rx),
                "ry": float(safe_pose.ry),
                "rz": float(safe_pose.rz),
                "fig": int(getattr(safe_pose, "fig", 1))
            },
            "useful_rect_px": useful_rect_px if useful_rect_px else [],
            "markers": [],
            "device_touch_interaction": device_touch_interaction
            
        }

        for m in marker_infos:
            pose = touch_poses_dict.get(m.marker_id)
            if pose:
                calibration_map["markers"].append({
                    "marker_id": int(m.marker_id),
                    "pixel_x": float(m.centroid[0]),
                    "pixel_y": float(m.centroid[1]),
                    "robot_x": float(pose.x),
                    "robot_y": float(pose.y),
                    "robot_z": float(pose.z)
                })

        # Salva o arquivo
        out_path = CalibrationMapExporter._resolve_output_path(
            output_dir=output_dir,
            device_type=device_type,
            device_model=device_model,
            dir_separation=dir_separation,
        )
        out_path.mkdir(parents=True, exist_ok=True)
        # human-readable timestamp for filename
        ts_str = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        filename = out_path / f"physical_calibration_map_{ts_str}_{int(time.time())}.json"
        
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(calibration_map, f, indent=4)
            logging.info(f"Mapa salvo com sucesso em: {filename}")
            return True
        except Exception as e:
            logging.error(f"Erro ao salvar mapa: {e}")
            return False