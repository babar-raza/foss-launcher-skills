def test_main_sequence_not_none(self):
        with Presentation() as pres:
            seq = pres.slides[0].timeline.main_sequence
            assert seq is not None