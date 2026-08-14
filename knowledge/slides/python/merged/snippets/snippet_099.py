def test_3d_bubble_chart_type_is_preserved(self):
        """Regression: add_chart(BUBBLE_WITH_3D) → chart.type must return
        BUBBLE_WITH_3D (not BUBBLE). The distinguishing bubble3D marker
        lives in <c:ser> which doesn't exist at chart creation time, so
        type detection alone would pick BUBBLE.
        """
        pres = Presentation()
        chart = pres.slides[0].shapes.add_chart(
            ChartType.BUBBLE_WITH_3D, 50, 50, 500, 400, False)
        assert chart.type == ChartType.BUBBLE_WITH_3D