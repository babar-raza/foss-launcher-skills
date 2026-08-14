def test_scatter_multi_series_round_trip(self, tmp_pptx):
        """Two scatter series each keep their own X/Y values."""
        pres = Presentation()
        chart = _add_clean_chart(pres, ChartType.SCATTER_WITH_MARKERS)

        data1 = [(1.0, 1.0), (2.0, 2.0), (3.0, 3.0)]
        s1 = chart.chart_data.series.add("A", ChartType.SCATTER_WITH_MARKERS)
        for x, y in data1:
            s1.data_points.add_data_point_for_scatter_series(x, y)

        data2 = [(1.5, 5.0), (2.5, 6.0), (3.5, 7.0)]
        s2 = chart.chart_data.series.add("B", ChartType.SCATTER_WITH_MARKERS)
        for x, y in data2:
            s2.data_points.add_data_point_for_scatter_series(x, y)

        pres2 = tmp_pptx(pres)
        series = list(_first_chart(pres2).chart_data.series)
        assert len(series) == 2
        for s, expected in zip(series, [data1, data2]):
            for dp, (x, y) in zip(s.data_points, expected):
                assert dp.x_value.as_literal_double == pytest.approx(x)
                assert dp.y_value.as_literal_double == pytest.approx(y)