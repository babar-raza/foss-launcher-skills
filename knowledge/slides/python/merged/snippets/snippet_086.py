def test_bubble_round_trip_xys(self, tmp_pptx):
        """Save/reload preserves X, Y, and size for bubble series."""
        pres = Presentation()
        chart = _add_clean_chart(pres, ChartType.BUBBLE)
        s = chart.chart_data.series.add("Companies", ChartType.BUBBLE)
        expected = [(1.0, 10.0, 5), (2.5, 22.0, 18), (4.0, 15.0, 40), (5.5, 28.0, 65)]
        for x, y, sz in expected:
            s.data_points.add_data_point_for_bubble_series(x, y, sz)

        pres2 = tmp_pptx(pres)
        s2 = _first_chart(pres2).chart_data.series[0]
        assert len(s2.data_points) == len(expected)
        for dp, (x, y, sz) in zip(s2.data_points, expected):
            assert dp.x_value.as_literal_double == pytest.approx(x)
            assert dp.y_value.as_literal_double == pytest.approx(y)
            assert dp.bubble_size.as_literal_double == pytest.approx(sz)