def test_add_fly_effect_with_subtype(self):
        with Presentation() as pres:
            slide = pres.slides[0]
            shape = slide.shapes.add_auto_shape(ShapeType.RECTANGLE, 10, 10, 100, 50)
            seq = slide.timeline.main_sequence

            effect = seq.add_effect(
                shape, anim.EffectType.FLY,
                anim.EffectSubtype.LEFT,
                anim.EffectTriggerType.ON_CLICK,
            )

            assert effect.type == anim.EffectType.FLY
            assert effect.subtype == anim.EffectSubtype.LEFT