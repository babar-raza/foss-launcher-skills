def test_entrance_effect_has_set_behavior(self):
        """Entrance effects get a default <p:set> visibility behavior."""
        with Presentation() as pres:
            slide = pres.slides[0]
            shape = slide.shapes.add_auto_shape(ShapeType.RECTANGLE, 10, 10, 100, 50)
            effect = slide.timeline.main_sequence.add_effect(
                shape, anim.EffectType.FADE,
                anim.EffectSubtype.NONE,
                anim.EffectTriggerType.ON_CLICK,
            )
            assert effect.behaviors.count >= 1
            assert isinstance(effect.behaviors[0], anim.SetEffect)