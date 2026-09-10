def test_remove_effect(self):
        with Presentation() as pres:
            slide = pres.slides[0]
            shape = slide.shapes.add_auto_shape(ShapeType.RECTANGLE, 10, 10, 100, 50)
            seq = slide.timeline.main_sequence
            eff = seq.add_effect(shape, anim.EffectType.FADE, anim.EffectSubtype.NONE,
                                 anim.EffectTriggerType.ON_CLICK)
            assert seq.count == 1
            seq.remove(eff)
            assert seq.count == 0