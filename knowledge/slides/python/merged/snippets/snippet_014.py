def test_default_trigger_type(self):
        with Presentation() as pres:
            slide = pres.slides[0]
            shape = slide.shapes.add_auto_shape(ShapeType.RECTANGLE, 10, 10, 100, 50)
            effect = slide.timeline.main_sequence.add_effect(
                shape, anim.EffectType.FADE,
                anim.EffectSubtype.NONE,
                anim.EffectTriggerType.ON_CLICK,
            )
            assert effect.timing.trigger_type == anim.EffectTriggerType.ON_CLICK