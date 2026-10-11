def test_timeline_not_none(self):
        with Presentation() as pres:
            tl = pres.slides[0].timeline
            assert tl is not None