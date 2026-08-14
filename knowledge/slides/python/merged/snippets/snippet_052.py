def test_add_effect_multiple_paragraphs(self):
        """Different paragraphs can each have their own animation."""
        with Presentation() as pres:
            slide = pres.slides[0]
            shape, paras = self._make_shape_with_paragraphs(slide)
            seq = slide.timeline.main_sequence

            seq.add_effect(paras[0], anim.EffectType.FLY,
                           anim.EffectSubtype.LEFT,
                           anim.EffectTriggerType.ON_CLICK)
            seq.add_effect(paras[2], anim.EffectType.FADE,
                           anim.EffectSubtype.NONE,
                           anim.EffectTriggerType.AFTER_PREVIOUS)

            assert len(seq.get_effects_by_paragraph(paras[0])) == 1
            assert len(seq.get_effects_by_paragraph(paras[1])) == 0
            assert len(seq.get_effects_by_paragraph(paras[2])) == 1
            assert seq.count == 2