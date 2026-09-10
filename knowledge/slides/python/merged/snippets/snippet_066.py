def test_interactive_sequence_add_effect(self):
        with Presentation() as pres:
            slide = pres.slides[0]
            trigger = slide.shapes.add_auto_shape(ShapeType.BEVEL, 10, 10, 20, 20)
            target = slide.shapes.add_auto_shape(ShapeType.RECTANGLE, 100, 100, 200, 100)

            seq = slide.timeline.interactive_sequences.add(trigger)
            effect = seq.add_effect(
                target, anim.EffectType.FADE,
                anim.EffectSubtype.NONE,
                anim.EffectTriggerType.ON_CLICK,
            )
            assert seq.count == 1
            assert effect.type == anim.EffectType.FADE