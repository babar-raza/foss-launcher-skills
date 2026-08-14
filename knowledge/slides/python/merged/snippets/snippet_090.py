def test_bubble_multi_series_round_trip(self, tmp_pptx):
        """Two bubble series keep their own X/Y/size values."""
        pres = Presentation()
        chart = _add_clean_chart(pres, ChartType.BUBBLE)
        data1 = [(1.0, 10.0, 5), (2.0, 20.0, 10)]
        s1 = chart.chart_data.series.add("A", ChartType.BUBBLE)
        for x, y, sz in data1:
            s1.data_points.add_data_point_for_bubble_series(x, y, sz)

        data2 = [(3.0, 30.0, 15), (4.0, 40.0, 20)]
        s2 = chart.chart_data.series.add("B", ChartType.BUBBLE)
        for x, y, sz in data2:
            s2.data_points.add_data_point_for_bubble_series(x, y, sz)

        pres2 = tmp_pptx(pres)
        series = list(_first_chart(pres2).chart_data.series)
        assert len(series) == 2
        for s, expected in zip(series, [data1, data2]):
            for dp, (x, y, sz) in zip(s.data_points, expected):
                assert dp.x_value.as_literal_double == pytest.approx(x)
                assert dp.y_value.as_literal_double == pytest.approx(y)
                assert dp.bubble_size.as_literal_double == pytest.approx(sz)