def test_get_or_create_by_value_custom(self):
        bp = anim.BehaviorProperty()
        result = bp.get_or_create_by_value('my.custom.prop')
        assert result.value == 'my.custom.prop'
        assert result.is_custom is True