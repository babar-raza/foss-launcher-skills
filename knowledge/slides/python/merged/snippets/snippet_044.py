def test_effect_type_values(self):
        assert anim.EffectType.APPEAR.value == 'Appear'
        assert anim.EffectType.FADE.value == 'Fade'
        assert anim.EffectType.FLY.value == 'Fly'
        assert anim.EffectType.PATH_USER.value == 'PathUser'