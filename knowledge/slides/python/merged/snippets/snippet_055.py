def test_multiple_effects_persist(self, tmp_pptx):
        pres = Presentation()
        slide = pres.slides[0]
        s1 = slide.shapes.add_auto_shape(ShapeType.RECTANGLE, 10, 10, 100, 50)
        s2 = slide.shapes.add_auto_shape(ShapeType.ELLIPSE, 200, 10, 100, 50)
        seq = slide.timeline.main_sequence
        seq.add_effect(s1, anim.EffectType.FADE, anim.EffectSubtype.NONE,
                       anim.EffectTriggerType.ON_CLICK)
        seq.add_effect(s2, anim.EffectType.APPEAR, anim.EffectSubtype.NONE,
                       anim.EffectTriggerType.AFTER_PREVIOUS)

        pres2 = tmp_pptx(pres)
        seq2 = pres2.slides[0].timeline.main_sequence
        assert seq2.count == 2
        assert seq2[0].type == anim.EffectType.FADE
        assert seq2[1].type == anim.EffectType.APPEAR
        pres2.dispose()