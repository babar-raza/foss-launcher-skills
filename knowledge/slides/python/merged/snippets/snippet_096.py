def test_paragraph_animation_round_trip(self):
        """Paragraph animation survives save/load cycle."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "para_anim.pptx")

            # Create and save
            with Presentation() as pres:
                slide = pres.slides[0]
                shape, paras = self._make_shape_with_paragraphs(slide)
                seq = slide.timeline.main_sequence
                seq.add_effect(paras[0], anim.EffectType.FLY,
                               anim.EffectSubtype.LEFT,
                               anim.EffectTriggerType.ON_CLICK)
                pres.save(path, SaveFormat.PPTX)

            # Reload and verify
            with Presentation(path) as pres:
                slide = pres.slides[0]
                seq = slide.timeline.main_sequence
                assert seq.count == 1

                # Find the animated shape
                animated_shape = None
                for i in range(len(slide.shapes)):
                    s = slide.shapes[i]
                    if len(seq.get_effects_by_shape(s)) > 0:
                        animated_shape = s
                        break
                assert animated_shape is not None

                tf = animated_shape.text_frame
                p0 = tf.paragraphs[0]
                effs = seq.get_effects_by_paragraph(p0)
                assert len(effs) == 1
                assert effs[0].type == anim.EffectType.FLY