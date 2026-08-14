def test_effect_subtype_values(self):
        assert anim.EffectSubtype.NONE.value == 'None'
        assert anim.EffectSubtype.LEFT.value == 'Left'
        assert anim.EffectSubtype.RIGHT.value == 'Right'