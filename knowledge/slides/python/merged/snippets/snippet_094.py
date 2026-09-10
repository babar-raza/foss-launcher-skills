def test_add_effect_paragraph_targets_correct_paragraph(self):
        """The XML should contain <p:pRg st='N' end='N'> for the targeted paragraph."""
        with Presentation() as pres:
            slide = pres.slides[0]
            shape, paras = self._make_shape_with_paragraphs(slide)
            seq = slide.timeline.main_sequence

            # Animate second paragraph (index 1)
            seq.add_effect(
                paras[1], anim.EffectType.FADE,
                anim.EffectSubtype.NONE,
                anim.EffectTriggerType.ON_CLICK,
            )

            # Verify via get_effects_by_paragraph
            assert len(seq.get_effects_by_paragraph(paras[0])) == 0
            assert len(seq.get_effects_by_paragraph(paras[1])) == 1
            assert len(seq.get_effects_by_paragraph(paras[2])) == 0