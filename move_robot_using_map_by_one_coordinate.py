"""Move the robot using a previously saved calibration map."""

from __future__ import annotations
from pathlib import Path

from drivers.robot.denso_aether import Denso
from utils.calibration_map import CalibrationMap
from to_get_x_e_y import CoordinateTransformer


DEFAULT_MAP_PATH ="physical_calibration_map.json"

def _validate_pixel_inside_useful_rect(cal_map: CalibrationMap, pixel_x: float, pixel_y: float) -> None:
    """Raise an error when the requested pixel is outside the saved useful area."""
    if len(cal_map.useful_rect_px) != 4:
        raise ValueError(
            "Invalid calibration map: useful_rect_px is missing or incomplete.")

    x_min, y_min, x_max, y_max = cal_map.useful_rect_px
    if not (x_min <= pixel_x <= x_max and y_min <= pixel_y <= y_max):
        raise ValueError(
            f"Target pixel ({pixel_x}, {pixel_y}) is outside the useful screen area "
            f"[{x_min}, {y_min}, {x_max}, {y_max}]."
        )


def execute_keyboard() -> int:
    """Load a calibration map and move the robot sequentially to multiple targets."""

    map_path = Path(DEFAULT_MAP_PATH)
    if not map_path.exists():
        raise FileNotFoundError(f"Calibration map not found: {map_path}")
    cal_map = CalibrationMap.from_file(map_path)
    transformer = CoordinateTransformer(cal_map)
    
    # 1. Seu dicionário de coordenadas de destino { ID: [pixel_x, pixel_y] }
    percentage_keys_dict = {1: [7.6, 69.5], 2: [16.9, 69.5], 3: [26.3, 69.5], 4: [35.6, 69.5], 5: [45.1, 69.5], 6: [54.5, 69.5], 7: [64.0, 69.5], 8: [73.4, 69.5], 9: [82.9, 69.5], 0: [92.3, 69.5],
    "q": [7.6, 74.9], "w": [16.9, 74.9], "e": [26.3, 74.9], "r": [35.6, 74.9], "t": [45.1, 74.9], "y": [54.5, 74.9], "u": [64.0, 74.9], "i": [73.4, 74.9], "o": [82.9, 74.9], "p": [92.3, 74.9], 
    "a": [12.3, 80.5], "s": [21.7, 80.5], "d": [31.0, 80.5], "f": [40.4, 80.5], "g": [49.8, 80.5], "h": [59.3, 80.5], "j": [68.7, 80.5], "k": [78.1, 80.5], "l": [87.6, 80.5], 
    "z": [21.7, 86.0], "x": [31.0, 86.0], "c": [40.4, 86.0], "v": [49.8, 86.0], "b": [59.3, 86.0], "n": [68.7, 86.0], "m": [78.1, 86.0]}

    # 2. Converta as coordenadas de porcentagem para pixels
    keys_dict = {}
    from pdb import set_trace; set_trace()
    keys_dict = transformer.get_transformed_coordinates(percentage_keys_dict)

    robot = Denso(
            workspace_name="RTA_WORKSPACE",
            control_name="rta",
            options="Server=192.168.160.225",
        )
    if robot is not None:
        if not robot.connect():
            raise RuntimeError("Failed to connect to the robot.")
        if not robot.motor_on():
            raise RuntimeError("Failed to enable robot motor.")
        
        robot.set_arm_speed(50, 25, 25)
        
        current_pose = robot.get_cartesian_pose()
        if current_pose is None:
            raise RuntimeError("Failed to read current robot pose.")
        pose_class = current_pose.__class__
        fig = int(getattr(current_pose, "fig", 5))

    try:
        # 3. Loop para percorrer o dicionário
        for key_id, coordinates in keys_dict.items():
            px_x, px_y = coordinates
            print(f"\n--- Processando ponto ID {key_id}: ({px_x}, {px_y}) ---")
            
            # Validação do ponto atual
            _validate_pixel_inside_useful_rect(cal_map, px_x, px_y)
            
            # Cálculo da pose de destino (com o ajuste comentado por você)
            target_pose = cal_map.to_pose_data(px_x, px_y)

            print(
                f"ID {key_id} - Pose interpolada calculada:",
                {
                    "x": target_pose.x, "y": target_pose.y, "z": target_pose.z,
                    "rx": target_pose.rx, "ry": target_pose.ry, "rz": target_pose.rz,
                },
            )

            # Configuração de aproximação e toque
            touch_z_offset_mm = 1.0
            touch_lift_offset_mm = 18.0

            approach_pose = pose_class(
                x=target_pose.x, y=target_pose.y, z=target_pose.z + touch_lift_offset_mm,
                rx=target_pose.rx, ry=target_pose.ry, rz=target_pose.rz, fig=fig,
            )
            touch_pose = pose_class(
                x=target_pose.x, y=target_pose.y, z=target_pose.z - touch_z_offset_mm,
                rx=target_pose.rx, ry=target_pose.ry, rz=target_pose.rz, fig=fig,
            )

            print(f"ID {key_id} - Movendo robô para o ponto...")
            if not robot.move_cartesian(approach_pose):
                raise RuntimeError(f"Failed to move above touch point for ID {key_id}.")

            if not robot.move_cartesian(touch_pose):
                raise RuntimeError(f"Failed to touch target point for ID {key_id}.")

            if not robot.move_cartesian(approach_pose):
                raise RuntimeError(f"Failed to retreat from touch point for ID {key_id}.")

        return 0

    finally:
        # if not args.dry_run:
        if robot is not None:
            try:
                robot.move_to_roi()
                robot.disconnect()
            except Exception:
                pass


# if __name__ == "__main__":
#     raise SystemExit(main())