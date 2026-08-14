def test_interactive_sequences_initially_empty(self):
        with Presentation() as pres:
            assert len(pres.slides[0].timeline.interactive_sequences) == 0