def test_scatter_round_trip_xy_values(self, tmp_pptx):
        """Save/reload preserves X and Y values for scatter series."""
        pres = Presentation()
        chart = _add_clean_chart(pres, ChartType.SCATTER_WITH_MARKERS)
        s = chart.chart_data.series.add("Data", ChartType.SCATTER_WITH_MARKERS)
        expected = [(1.0, 2.5), (2.5, 4.1), (4.2, 3.3), (6.1, 5.8)]
        for x, y in expected:
            s.data_points.add_data_point_for_scatter_series(x, y)

        pres2 = tmp_pptx(pres)
        s2 = _first_chart(pres2).chart_data.series[0]
        assert len(s2.data_points) == len(expected)
        for dp, (x, y) in zip(s2.data_points, expected):
            assert dp.x_value is not None, "x_value must survive round-trip"
            assert dp.y_value is not None, "y_value must survive round-trip"
            assert dp.x_value.as_literal_double == pytest.approx(x)
            assert dp.y_value.as_literal_double == pytest.approx(y)