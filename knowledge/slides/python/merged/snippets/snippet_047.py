def test_main_sequence_initially_empty(self):
        with Presentation() as pres:
            assert pres.slides[0].timeline.main_sequence.count == 0