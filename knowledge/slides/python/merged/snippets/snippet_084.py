def test_get_or_create_by_value_predefined(self):
        bp = anim.BehaviorProperty()
        result = bp.get_or_create_by_value('ppt_x')
        assert result is bp.ppt_x