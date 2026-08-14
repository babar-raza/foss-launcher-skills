def test_add_interactive_sequence(self):
        with Presentation() as pres:
            slide = pres.slides[0]
            trigger = slide.shapes.add_auto_shape(ShapeType.BEVEL, 10, 10, 20, 20)
            target = slide.shapes.add_auto_shape(ShapeType.RECTANGLE, 100, 100, 200, 100)

            seq = slide.timeline.interactive_sequences.add(trigger)
            assert seq is not None
            assert len(slide.timeline.interactive_sequences) == 1