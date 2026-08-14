def test_all_scatter_subtypes_round_trip(self, chart_type, tmp_pptx):
        """Each scatter subtype preserves X/Y values through save/reload."""
        pres = Presentation()
        chart = _add_clean_chart(pres, chart_type)
        s = chart.chart_data.series.add("S", chart_type)
        expected = [(0.0, 0.0), (1.0, 2.0), (2.0, 1.5), (3.0, 4.0)]
        for x, y in expected:
            s.data_points.add_data_point_for_scatter_series(x, y)

        pres2 = tmp_pptx(pres)
        s2 = _first_chart(pres2).chart_data.series[0]
        for dp, (x, y) in zip(s2.data_points, expected):
            assert dp.x_value.as_literal_double == pytest.approx(x)
            assert dp.y_value.as_literal_double == pytest.approx(y)