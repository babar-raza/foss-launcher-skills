def test_remove_by_shape(self):
        with Presentation() as pres:
            slide = pres.slides[0]
            s1 = slide.shapes.add_auto_shape(ShapeType.RECTANGLE, 10, 10, 100, 50)
            s2 = slide.shapes.add_auto_shape(ShapeType.ELLIPSE, 200, 10, 100, 50)
            seq = slide.timeline.main_sequence
            seq.add_effect(s1, anim.EffectType.FADE, anim.EffectSubtype.NONE,
                           anim.EffectTriggerType.ON_CLICK)
            seq.add_effect(s2, anim.EffectType.APPEAR, anim.EffectSubtype.NONE,
                           anim.EffectTriggerType.ON_CLICK)
            seq.add_effect(s1, anim.EffectType.FLY, anim.EffectSubtype.LEFT,
                           anim.EffectTriggerType.AFTER_PREVIOUS)

            seq.remove_by_shape(s1)
            assert seq.count == 1
            assert seq[0].type == anim.EffectType.APPEAR