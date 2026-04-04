
class RtaModel:
    # Auto generated code adjusted to valid Python syntax.

    RESULT_NONE = "none"
    RESULT_SUCCESS = "success"
    RESULT_FAILURE = "failure"

    def __init__(self, num_markers=4):
        self.num_markers = max(1, int(num_markers))
        self.marker_index = 0

        self.max_connect_robot_attempts = 3
        self.max_motor_on_attempts = 3
        self.connect_robot_attempt = 0
        self.motor_on_attempt = 0

        self.aligned_flag = False
        self.robot_connected_flag = False
        self.motor_on_flag = False
        self.camera_on_flag = False
        self.markers_found_flag = False
        self.touch_ok_flag = False
        self.swipe_executed_flag = False

        self.detect_markers_attempts = 0
        self.error_touch = 0
        self.final_result_failures = 0
        self.final_result = self.RESULT_NONE
        self.denso_robot = None

        # Optional integration hooks (inject callables from application layer).
        self.move_to_roi_fn = None
        self.camera_on_fn = None
        self.detect_markers_fn = None
        self.align_with_markers_fn = None
        self.touch_marker_fn = None
        self.check_touch_fn = None
        self.reset_markers_fn = None
        self.generate_map_fn = None
        self.swipe_borders_fn = None
        self.safe_pose_fn = None
        self.read_final_marker_fn = None
        self.return_to_start_fn = None
        self.save_map_fn = None

    def set_aligned_false(self):
        self.aligned_flag = False

    def marker_index_eq_num_markers(self):
        return self.marker_index == self.num_markers

    def set_motor_on_false(self):
        self.motor_on_flag = False

    def increment_detect_markers_attempts(self):
        self.detect_markers_attempts += 1

    def set_swipe_executed_false(self):
        self.swipe_executed_flag = False

    def increment_error_touch(self):
        self.error_touch += 1

    def increment_final_result_failures(self):
        self.final_result_failures += 1

    def set_aligned_true(self):
        self.aligned_flag = True

    def robot_connected(self):
        return self.robot_connected_flag

    def increment_marker_index(self):
        self.marker_index += 1

    def aligned(self):
        return self.aligned_flag

    def set_camera_on_true(self):
        self.camera_on_flag = True

    def set_motor_on_true(self):
        self.motor_on_flag = True

    def final_result_is_failure(self):
        return self.final_result == self.RESULT_FAILURE

    def set_markers_found_false(self):
        self.markers_found_flag = False

    def final_result_is_success(self):
        return self.final_result == self.RESULT_SUCCESS

    def marker_index_lt_num_markers_minus_one(self):
        return self.marker_index < self.num_markers - 1

    def swipe_executed(self):
        return self.swipe_executed_flag

    def final_result_failures_gte_fifteen(self):
        return self.final_result_failures >= 15

    def set_final_result_none(self):
        self.final_result = self.RESULT_NONE

    def motor_on(self):
        return self.motor_on_flag

    def camera_on(self):
        return self.camera_on_flag

    def touch_ok(self):
        return self.touch_ok_flag

    def error_touch_gte_fifteen(self):
        return self.error_touch >= 15

    def detect_markers_attempts_gte_twenty(self):
        return self.detect_markers_attempts >= 20

    def connect_robot_attempts_gte_max(self):
        return self.connect_robot_attempt >= self.max_connect_robot_attempts

    def motor_on_attempts_gte_max(self):
        return self.motor_on_attempt >= self.max_motor_on_attempts

    def always_true(self):
        return True

    def marker_index_lt_num_markers(self):
        return self.marker_index < self.num_markers

    def set_touch_ok_false(self):
        self.touch_ok_flag = False

    def markers_found(self):
        return self.markers_found_flag

    def marker_index_eq_num_markers_minus_one(self):
        return self.marker_index == self.num_markers - 1

    def set_robot_connected_true(self):
        self.robot_connected_flag = True

    def set_swipe_executed_true(self):
        self.swipe_executed_flag = True

    def set_marker_index_zero(self):
        self.marker_index = 0

    #=======================================
    def connect_robot_action(self):
        """Try to connect using the injected robot adapter.

        If no adapter is configured, keep the flag as False.
        """
        self.connect_robot_attempt += 1

        if self.denso_robot is None:
            self.robot_connected_flag = False
            return

        try:
            self.robot_connected_flag = bool(self.denso_robot.connect())
            if self.robot_connected_flag:
                self.connect_robot_attempt = 0
        except Exception:
            self.robot_connected_flag = False

    def turn_motor_on_action(self):
        """Try to enable motor after the robot is connected."""
        self.motor_on_attempt += 1

        if not self.robot_connected_flag or self.denso_robot is None:
            self.motor_on_flag = False
            return

        try:
            self.motor_on_flag = bool(self.denso_robot.motor_on())
            if self.motor_on_flag:
                self.motor_on_attempt = 0
        except Exception:
            self.motor_on_flag = False

    def turn_motor_off_action(self):
        """Try to disable motor and always clear the local flag."""
        if self.denso_robot is None:
            self.motor_on_flag = False
            return

        try:
            self.denso_robot.motor_off()
        except Exception:
            pass

        self.motor_on_flag = False

    def move_to_roi_action(self):
        if callable(self.move_to_roi_fn):
            self.move_to_roi_fn()

    def camera_on_action(self):
        if callable(self.camera_on_fn):
            try:
                self.camera_on_flag = bool(self.camera_on_fn())
                return
            except Exception:
                pass

        self.camera_on_flag = True

    def detect_markers_action(self):
        """Try marker detection and update markers_found flag."""
        if callable(self.detect_markers_fn):
            try:
                result = self.detect_markers_fn()
                self.markers_found_flag = bool(result)
                if self.markers_found_flag:
                    self.detect_markers_attempts = 0
                return
            except Exception:
                self.markers_found_flag = False
                return

        # Default fallback allows state machine progression when no integration
        # callback has been connected yet.
        self.markers_found_flag = True
        self.detect_markers_attempts = 0

    def align_with_markers_action(self):
        if callable(self.align_with_markers_fn):
            try:
                self.aligned_flag = bool(self.align_with_markers_fn())
                return
            except Exception:
                pass

        self.aligned_flag = self.markers_found_flag

    def touch_marker_action(self):
        if callable(self.touch_marker_fn):
            try:
                self.touch_ok_flag = bool(self.touch_marker_fn(self.marker_index))
                return
            except Exception:
                pass

        self.touch_ok_flag = True

    def check_touch_action(self):
        if callable(self.check_touch_fn):
            try:
                self.touch_ok_flag = bool(self.check_touch_fn(self.marker_index))
                return
            except Exception:
                pass

    def reset_markers_action(self):
        if callable(self.reset_markers_fn):
            try:
                self.reset_markers_fn()
            except Exception:
                pass

    def generate_map_action(self):
        if callable(self.generate_map_fn):
            try:
                self.generate_map_fn()
            except Exception:
                pass

    def swipe_borders_action(self):
        if callable(self.swipe_borders_fn):
            try:
                self.swipe_executed_flag = bool(self.swipe_borders_fn())
                return
            except Exception:
                pass

    def safe_pose_action(self):
        if callable(self.safe_pose_fn):
            try:
                self.safe_pose_fn()
            except Exception:
                pass

    def read_final_marker_action(self):
        if callable(self.read_final_marker_fn):
            try:
                result = self.read_final_marker_fn()
                if result in (self.RESULT_SUCCESS, self.RESULT_FAILURE):
                    self.final_result = result
                    return
                if isinstance(result, str):
                    if result.lower() == self.RESULT_SUCCESS:
                        self.final_result = self.RESULT_SUCCESS
                        return
                    if result.lower() == self.RESULT_FAILURE:
                        self.final_result = self.RESULT_FAILURE
                        return
            except Exception:
                pass

        self.final_result = self.RESULT_SUCCESS

    def return_to_start_action(self):
        if callable(self.return_to_start_fn):
            try:
                self.return_to_start_fn()
            except Exception:
                pass

    def save_map_action(self):
        if callable(self.save_map_fn):
            try:
                self.save_map_fn()
            except Exception:
                pass