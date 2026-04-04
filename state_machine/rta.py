from transitions import State
from transitions.extensions import GraphMachine


class Rta(GraphMachine):

    def __init__(self, model) -> None:
        """Constructor of the base `Rta` class.
        """
        idle = State(
            name='idle',
        )
        connect_robot = State(
            name='connect_robot',
            on_enter=['connect_robot_action'],
        )
        motor_on = State(
            name='motor_on',
            on_enter=['turn_motor_on_action'],
        )
        move_to_roi = State(
            name='move_to_roi',
            on_enter=['move_to_roi_action'],
        )
        camera_on = State(
            name='camera_on',
            on_enter=['camera_on_action'],
        )
        detect_markers = State(
            name='detect_markers',
            on_enter=['detect_markers_action'],
        )
        align_with_markers = State(
            name='align_with_markers',
            on_enter=['align_with_markers_action'],
        )
        touch_marker = State(
            name='touch_marker',
            on_enter=['touch_marker_action'],
        )
        check_touch = State(
            name='check_touch',
            on_enter=['check_touch_action'],
        )
        reset_markers = State(
            name='reset_markers',
            on_enter=['reset_markers_action'],
        )
        generate_map = State(
            name='generate_map',
            on_enter=['generate_map_action'],
        )
        swipe_borders = State(
            name='swipe_borders',
            on_enter=['swipe_borders_action'],
        )
        safe_pose = State(
            name='safe_pose',
            on_enter=['safe_pose_action'],
        )
        read_final_marker = State(
            name='read_final_marker',
            on_enter=['read_final_marker_action'],
        )
        return_to_start = State(
            name='return_to_start',
            on_enter=['return_to_start_action'],
        )
        save_map = State(
            name='save_map',
            on_enter=['save_map_action'],
        )
        done = State(
            name='done',
        )
        motor_off = State(
            name='motor_off',
            on_enter=['turn_motor_off_action'],
        )
        error = State(
            name='error',
        )

        states = [
            idle,
            connect_robot,
            motor_on,
            move_to_roi,
            camera_on,
            detect_markers,
            align_with_markers,
            touch_marker,
            check_touch,
            reset_markers,
            generate_map,
            swipe_borders,
            safe_pose,
            read_final_marker,
            return_to_start,
            save_map,
            done,
            motor_off,
            error,
        ]

        transitions = [
            {'trigger': 'read_final_marker_to_error', 'source': 'read_final_marker', 'dest': 'error', 'conditions': ['final_result_failures_gte_fifteen']},
            {'trigger': 'check_touch_to_error', 'source': 'check_touch', 'dest': 'error', 'conditions': ['error_touch_gte_fifteen']},
            {'trigger': 'detect_markers_to_error', 'source': 'detect_markers', 'dest': 'error', 'conditions': ['detect_markers_attempts_gte_twenty']},
            {'trigger': 'motor_off_to_done', 'source': 'motor_off', 'dest': 'done', 'after': ['set_motor_on_false']},
            {'trigger': 'save_map_to_motor_off', 'source': 'save_map', 'dest': 'motor_off', 'conditions': ['always_true']},
            {'trigger': 'read_final_marker_to_save_map', 'source': 'read_final_marker', 'dest': 'save_map', 'conditions': ['final_result_is_success'], 'after': ['always_true']},
            {'trigger': 'return_to_start_to_move_to_roi', 'source': 'return_to_start', 'dest': 'move_to_roi', 'conditions': ['always_true'], 'after': ['set_markers_found_false', 'set_aligned_false', 'set_touch_ok_false', 'set_swipe_executed_false', 'set_final_result_none', 'set_marker_index_zero']},
            {'trigger': 'read_final_marker_to_return_to_start', 'source': 'read_final_marker', 'dest': 'return_to_start', 'conditions': ['final_result_is_failure'], 'after': ['always_true', 'increment_final_result_failures']},
            {'trigger': 'safe_pose_to_read_final_marker', 'source': 'safe_pose', 'dest': 'read_final_marker', 'conditions': ['swipe_executed'], 'after': ['always_true']},
            {'trigger': 'swipe_borders_to_safe_pose', 'source': 'swipe_borders', 'dest': 'safe_pose', 'conditions': ['always_true'], 'after': ['set_swipe_executed_true']},
            {'trigger': 'generate_map_to_swipe_borders', 'source': 'generate_map', 'dest': 'swipe_borders', 'conditions': ['marker_index_eq_num_markers'], 'after': ['set_swipe_executed_false']},
            {'trigger': 'check_touch_to_generate_map', 'source': 'check_touch', 'dest': 'generate_map', 'conditions': ['touch_ok', 'marker_index_eq_num_markers_minus_one'], 'after': ['increment_marker_index']},
            {'trigger': 'check_touch_to_touch_marker', 'source': 'check_touch', 'dest': 'touch_marker', 'conditions': ['touch_ok', 'marker_index_lt_num_markers_minus_one'], 'after': ['increment_marker_index']},
            {'trigger': 'reset_markers_to_move_to_roi', 'source': 'reset_markers', 'dest': 'move_to_roi'},
            {'trigger': 'check_touch_to_reset_markers', 'source': 'check_touch', 'dest': 'reset_markers', 'unless': ['touch_ok'], 'after': ['set_marker_index_zero', 'increment_error_touch']},
            {'trigger': 'detect_markers_to_detect_markers', 'source': 'detect_markers', 'dest': 'detect_markers', 'conditions': ['camera_on'], 'unless': ['markers_found'], 'after': ['set_markers_found_false', 'increment_detect_markers_attempts']},
            {'trigger': 'touch_marker_to_check_touch', 'source': 'touch_marker', 'dest': 'check_touch', 'conditions': ['aligned', 'marker_index_lt_num_markers'], 'after': ['always_true']},
            {'trigger': 'align_with_markers_to_touch_marker', 'source': 'align_with_markers', 'dest': 'touch_marker', 'conditions': ['markers_found'], 'after': ['set_aligned_true']},
            {'trigger': 'detect_markers_to_align_with_markers', 'source': 'detect_markers', 'dest': 'align_with_markers', 'conditions': ['camera_on', 'markers_found'], 'after': ['set_marker_index_zero']},
            {'trigger': 'camera_on_to_detect_markers', 'source': 'camera_on', 'dest': 'detect_markers', 'conditions': ['always_true'], 'after': ['set_camera_on_true']},
            {'trigger': 'move_to_roi_to_camera_on', 'source': 'move_to_roi', 'dest': 'camera_on', 'conditions': ['motor_on'], 'after': ['set_aligned_false', 'set_markers_found_false', 'set_touch_ok_false']},
            {'trigger': 'motor_on_to_error', 'source': 'motor_on', 'dest': 'error', 'conditions': ['motor_on_attempts_gte_max']},
            {'trigger': 'motor_on_to_motor_on', 'source': 'motor_on', 'dest': 'motor_on', 'unless': ['motor_on', 'motor_on_attempts_gte_max']},
            {'trigger': 'motor_on_to_move_to_roi', 'source': 'motor_on', 'dest': 'move_to_roi', 'conditions': ['motor_on']},
            {'trigger': 'connect_robot_to_error', 'source': 'connect_robot', 'dest': 'error', 'conditions': ['connect_robot_attempts_gte_max']},
            {'trigger': 'connect_robot_to_connect_robot', 'source': 'connect_robot', 'dest': 'connect_robot', 'unless': ['robot_connected', 'connect_robot_attempts_gte_max']},
            {'trigger': 'connect_robot_to_motor_on', 'source': 'connect_robot', 'dest': 'motor_on', 'conditions': ['robot_connected']},
            {'trigger': 'idle_to_connect_robot', 'source': 'idle', 'dest': 'connect_robot'},
        ]

        super().__init__(
            model=model,
            states=states,
            transitions=transitions,
            initial=idle,
        )

    def __getattr__(self, item):
        """Method to get unlisted attributes of the class. If the attribute
        is not found, the method will return the class attribute.

        Args:
            item: The class attribute that should be retrieved.

        Returns:
            The class attribute.
        """
        return self.model.__getattribute__(item)

    def next_state(self):
        """Method for automatic execution of available transitions in each
        of the machine states.
        """
        available_transitions = self.get_triggers(self.state)
        available_transitions = available_transitions[len(self.states):]

        for curr_transition in available_transitions:
            may_method_result = self.may_trigger(curr_transition)
            if may_method_result:
                self.trigger(curr_transition)
                break
