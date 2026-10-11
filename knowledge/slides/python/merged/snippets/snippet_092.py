def test_motion_command_path_type_values(self):
        assert anim.MotionCommandPathType.MOVE_TO.value == 'MoveTo'
        assert anim.MotionCommandPathType.LINE_TO.value == 'LineTo'
        assert anim.MotionCommandPathType.END.value == 'End'