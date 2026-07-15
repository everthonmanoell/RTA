from transitions import State
from transitions.extensions import GraphMachine


class Rta(GraphMachine):

    def __init__(self, model, offset_mode=None) -> None:
        """Constructor of the base `Rta` class."""
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
        detect_single_marker = State(
            name="detect_single_marker",
            on_enter=["detect_single_marker_action"],
        )
        center_camera = State(
            name="center_camera",
            on_enter=["center_camera_action"],
        )
        adjust_rz = State(
            name="adjust_rz",
            on_enter=["adjust_rz_action"],
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
        calibrate_z_touches = State(
            name='calibrate_z_touches',
            on_enter=['calibrate_z_touches_action'],
        )   

        # Definimos a lista base de estados SEM o offset_adjust
        states = [
            idle,
            connect_robot,
            motor_on,
            move_to_roi,
            camera_on,
            detect_single_marker,
            center_camera,
            adjust_rz,
            detect_markers,
            calibrate_z_touches,
            generate_map,
            swipe_borders,
            safe_pose,
            read_final_marker,
            save_map,
            done,
            motor_off,
            error,
        ]

        # Inserimos dinamicamente o estado offset_adjust apenas se for "auto"
        if offset_mode == "auto":
            offset_adjust = State(
                name='offset_adjust',
                on_enter=['offset_adjust_action'],
            )
            # Inserimos logo após o adjust_rz (posição 8 na lista) para manter a organização
            states.insert(8, offset_adjust)

        transitions = [
            {'trigger': 'motor_off_to_done', 'source': 'motor_off', 'dest': 'done', 'after': ['set_motor_on_false']},

            {'trigger': 'save_map_to_motor_off', 'source': 'save_map', 'dest': 'motor_off', 'conditions': ['save_map_ok']},
            {'trigger': 'save_map_to_error', 'source': 'save_map', 'dest': 'error', 'unless': ['save_map_ok']},

            {'trigger': 'read_final_marker_to_save_map', 'source': 'read_final_marker', 'dest': 'save_map', 'conditions': ['final_result_is_success']},
            {'trigger': 'read_final_marker_to_error', 'source': 'read_final_marker', 'dest': 'error', 'conditions': ['final_result_is_failure']},

            {'trigger': 'safe_pose_to_read_final_marker', 'source': 'safe_pose', 'dest': 'read_final_marker', 'conditions': ['safe_pose_ok']},
            {'trigger': 'safe_pose_to_error', 'source': 'safe_pose', 'dest': 'error', 'unless': ['safe_pose_ok']},

            {'trigger': 'swipe_borders_to_safe_pose', 'source': 'swipe_borders', 'dest': 'safe_pose', 'conditions': ['swipe_executed']},
            {'trigger': 'swipe_borders_to_error', 'source': 'swipe_borders', 'dest': 'error', 'unless': ['swipe_executed']},

            {'trigger': 'generate_map_to_swipe_borders', 'source': 'generate_map', 'dest': 'swipe_borders', 'conditions': ['map_generated']},
            {'trigger': 'generate_map_to_error', 'source': 'generate_map', 'dest': 'error', 'unless': ['map_generated']},

            {'trigger': 'calibrate_z_touches_to_generate_map', 'source': 'calibrate_z_touches', 'dest': 'generate_map', 'conditions': ['calibration_ok']},
            {'trigger': 'calibrate_z_touches_to_error', 'source': 'calibrate_z_touches', 'dest': 'error', 'unless': ['calibration_ok']},

            {'trigger': 'detect_markers_to_calibrate_z_touches', 'source': 'detect_markers', 'dest': 'calibrate_z_touches', 'conditions': ['markers_ready_for_align']},
            {'trigger': 'detect_markers_to_error', 'source': 'detect_markers', 'dest': 'error', 'conditions': ['detect_markers_attempts_gte_twenty']},
            {'trigger': 'detect_markers_to_detect_markers', 'source': 'detect_markers', 'dest': 'detect_markers', 'unless': ['markers_ready_for_align', 'detect_markers_attempts_gte_twenty']},

            {'trigger': 'camera_on_to_detect_single_marker', 'source': 'camera_on', 'dest': 'detect_single_marker', 'conditions': ['camera_on']},
            {'trigger': 'camera_on_to_error', 'source': 'camera_on', 'dest': 'error', 'conditions': ['camera_on_attempts_gte_max']},
            {'trigger': 'camera_on_to_camera_on', 'source': 'camera_on', 'dest': 'camera_on', 'unless': ['camera_on', 'camera_on_attempts_gte_max']},

            {'trigger': 'detect_single_marker_to_center_camera', 'source': 'detect_single_marker', 'dest': 'center_camera', 'conditions': ['single_marker_detected']},
            {'trigger': 'detect_single_marker_to_error', 'source': 'detect_single_marker', 'dest': 'error', 'conditions': ['detect_single_marker_attempts_gte_max']},
            {'trigger': 'detect_single_marker_to_detect_single_marker', 'source': 'detect_single_marker', 'dest': 'detect_single_marker', 'unless': ['single_marker_detected', 'detect_single_marker_attempts_gte_max']},

            {'trigger': 'center_camera_to_detect_markers', 'source': 'center_camera', 'dest': 'detect_markers', 'conditions': ['camera_centered', 'rz_already_adjusted']},
            {'trigger': 'center_camera_to_adjust_rz', 'source': 'center_camera', 'dest': 'adjust_rz', 'conditions': ['camera_centered'], 'unless': ['rz_already_adjusted']},
            {'trigger': 'center_camera_to_error', 'source': 'center_camera', 'dest': 'error', 'conditions': ['center_camera_attempts_gte_max']},
            {'trigger': 'center_camera_to_center_camera', 'source': 'center_camera', 'dest': 'center_camera', 'unless': ['camera_centered', 'center_camera_attempts_gte_max']},

            {'trigger': 'move_to_roi_to_camera_on', 'source': 'move_to_roi', 'dest': 'camera_on', 'conditions': ['move_to_roi_ok']},
            {'trigger': 'move_to_roi_to_error', 'source': 'move_to_roi', 'dest': 'error', 'unless': ['move_to_roi_ok']},

            {'trigger': 'motor_on_to_move_to_roi', 'source': 'motor_on', 'dest': 'move_to_roi', 'conditions': ['motor_on']},
            {'trigger': 'motor_on_to_error', 'source': 'motor_on', 'dest': 'error', 'conditions': ['motor_on_attempts_gte_max']},
            {'trigger': 'motor_on_to_motor_on', 'source': 'motor_on', 'dest': 'motor_on', 'unless': ['motor_on', 'motor_on_attempts_gte_max']},

            {'trigger': 'connect_robot_to_motor_on', 'source': 'connect_robot', 'dest': 'motor_on', 'conditions': ['robot_connected']},
            {'trigger': 'connect_robot_to_error', 'source': 'connect_robot', 'dest': 'error', 'conditions': ['connect_robot_attempts_gte_max']},
            {'trigger': 'connect_robot_to_connect_robot', 'source': 'connect_robot', 'dest': 'connect_robot', 'unless': ['robot_connected', 'connect_robot_attempts_gte_max']},

            {'trigger': 'idle_to_connect_robot', 'source': 'idle', 'dest': 'connect_robot'},
        ]

        # Configurações condicionais de rotas baseadas no parâmetro offset_mode
        if offset_mode == "auto":
            transitions.append(
                {'trigger': 'adjust_rz_to_offset_adjust', 'source': 'adjust_rz', 'dest': 'offset_adjust', 'conditions': ['rz_adjusted']}
            )
            transitions.append(
                {'trigger': 'adjust_rz_to_error', 'source': 'adjust_rz', 'dest': 'error', 'conditions': ['adjust_rz_attempts_gte_max']}
            )
            transitions.append(
                {'trigger': 'adjust_rz_to_adjust_rz', 'source': 'adjust_rz', 'dest': 'adjust_rz', 'unless': ['rz_adjusted', 'adjust_rz_attempts_gte_max']}
            )
            transitions.append(
                {'trigger': 'offset_adjust_to_detect_markers', 'source': 'offset_adjust', 'dest': 'detect_markers', 'conditions': ['offset_adjust_ok']}
            )
            transitions.append(
                {'trigger': 'offset_adjust_to_error', 'source': 'offset_adjust', 'dest': 'error', 'unless': ['offset_adjust_ok']}
            )
        else:
            # CORRIGIDO: Se não for "auto", adjust_rz aponta direto para detect_markers
            transitions.append(
                {'trigger': 'adjust_rz_to_detect_markers', 'source': 'adjust_rz', 'dest': 'detect_markers', 'conditions': ['rz_adjusted']}
            )
            transitions.append(
                {'trigger': 'adjust_rz_to_error', 'source': 'adjust_rz', 'dest': 'error', 'conditions': ['adjust_rz_attempts_gte_max']}
            )
            transitions.append(
                {'trigger': 'adjust_rz_to_adjust_rz', 'source': 'adjust_rz', 'dest': 'adjust_rz', 'unless': ['rz_adjusted', 'adjust_rz_attempts_gte_max']}
            )

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
