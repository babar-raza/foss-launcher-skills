def test_predefined_value(self):
        bp = anim.BehaviorProperty()
        assert bp.ppt_x.value == 'ppt_x'
        assert bp.ppt_x.is_custom is False