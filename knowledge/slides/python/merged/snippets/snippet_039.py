def test_style_visibility(self):
        bp = anim.BehaviorProperty()
        assert bp.style_visibility.value == 'style.visibility'