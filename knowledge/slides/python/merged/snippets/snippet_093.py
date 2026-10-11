def test_add_effect_paragraph_returns_effect(self):
        with Presentation() as pres:
            slide = pres.slides[0]
            shape, paras = self._make_shape_with_paragraphs(slide)
            seq = slide.timeline.main_sequence

            effect = seq.add_effect(
                paras[0], anim.EffectType.FLY,
                anim.EffectSubtype.LEFT,
                anim.EffectTriggerType.ON_CLICK,
            )
            assert effect is not None
            assert effect.type == anim.EffectType.FLY