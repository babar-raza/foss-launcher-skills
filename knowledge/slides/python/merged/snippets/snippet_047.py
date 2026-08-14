def test_effect_preset_class_type_values(self):
        assert anim.EffectPresetClassType.ENTRANCE.value == 'Entrance'
        assert anim.EffectPresetClassType.EXIT.value == 'Exit'
        assert anim.EffectPresetClassType.EMPHASIS.value == 'Emphasis'
        assert anim.EffectPresetClassType.PATH.value == 'Path'