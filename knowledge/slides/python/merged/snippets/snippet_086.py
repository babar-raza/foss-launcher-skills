def test_default_is_custom(self):
        bp = anim.BehaviorProperty()
        assert bp.is_custom is True
        assert bp.value == ''