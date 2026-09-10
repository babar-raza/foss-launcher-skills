def test_remove_at(self):
        with Presentation() as pres:
            slide = pres.slides[0]
            shape = slide.shapes.add_auto_shape(ShapeType.RECTANGLE, 10, 10, 100, 50)
            seq = slide.timeline.main_sequence
            seq.add_effect(shape, anim.EffectType.FADE, anim.EffectSubtype.NONE,
                           anim.EffectTriggerType.ON_CLICK)
            seq.add_effect(shape, anim.EffectType.APPEAR, anim.EffectSubtype.NONE,
                           anim.EffectTriggerType.AFTER_PREVIOUS)
            seq.remove_at(0)
            assert seq.count == 1
            assert seq[0].type == anim.EffectType.APPEAR