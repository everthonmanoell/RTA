**Move Robot Using Calibration Map — Single Coordinate**

Quick description: Uses an exported calibration map (JSON) to compute the robot pose corresponding to a screen pixel and runs a simple sequence: approach, touch, and retreat.

Prerequisites
- Python environment with the project dependencies installed (use `poetry install`).
- A calibration map JSON file exported by the exporter (e.g. `result_map/physical_calibration_map_...json`).
- Robot driver configured and reachable (the project uses `drivers.robot.denso_aether.Denso`).

File: move_robot_using_map_by_one_coordinate.py

Example command (PowerShell)
```powershell
poetry run python move_robot_using_map_by_one_coordinate.py \
  --workspace RTA_WORKSPACE \
  --control rta \
  --options "Server=192.168.160.225" \
  --json-path "result_map\physical_calibration_map_20260529_082315_1780053795.json" \
  --pixel-x 275 \
  --pixel-y 200
```

Single-line PowerShell example
```powershell
poetry run python move_robot_using_map_by_one_coordinate.py --workspace RTA_WORKSPACE --control rta --options "Server=192.168.160.225" --json-path "result_map\physical_calibration_map_20260529_082315_1780053795.json" --pixel-x 275 --pixel-y 200
```

Main arguments
- `--workspace`: Workspace identifier used by the driver/config (e.g. `RTA_WORKSPACE`).
- `--control`: Adapter/control name (e.g. `rta`).
- `--options`: Adapter option string (e.g. `"Server=192.168.160.225"`).
- `--json-path`: Path to the calibration map JSON file.
- `--pixel-x`: Target pixel X coordinate (integer).
- `--pixel-y`: Target pixel Y coordinate (integer).
- `--dry-run` (optional): If provided, the script will not send movement commands to the robot and will print planned actions instead.

Behavior and safety
- The script validates that the `(pixel-x, pixel-y)` pair is inside the `useful_rect_px` rectangle stored in the JSON; if the point is outside that rectangle the script aborts to avoid unsafe movements.
- The executed sequence is: move to an approach position above the target, descend to the touch Z, wait 0.2s, then retreat. Tweak parameters directly in the script if needed.
- Use `--dry-run` to inspect the interpolated pose before sending actual motions.

Example dry-run output
- The script prints the computed pose (x, y, z in mm) and the planned actions: `approach -> touch -> retreat`.

Notes
- To allow extrapolation outside `useful_rect_px`, modify the validation in `move_robot_using_map_by_one_coordinate.py` (the current behavior rejects pixels outside the rectangle).
- Always verify actuator state, safety limits and clear the workspace before running automated movements.

