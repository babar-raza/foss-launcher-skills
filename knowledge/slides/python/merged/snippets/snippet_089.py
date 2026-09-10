def test_effect_trigger_type_values(self):
        assert anim.EffectTriggerType.ON_CLICK.value == 'OnClick'
        assert anim.EffectTriggerType.WITH_PREVIOUS.value == 'WithPrevious'
        assert anim.EffectTriggerType.AFTER_PREVIOUS.value == 'AfterPrevious'