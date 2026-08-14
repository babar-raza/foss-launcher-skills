def test_scatter_marker_round_trip(self, tmp_pptx):
        """Series marker symbol/size persist across save/reload."""
        pres = Presentation()
        chart = _add_clean_chart(pres, ChartType.SCATTER_WITH_MARKERS)
        s = chart.chart_data.series.add("S", ChartType.SCATTER_WITH_MARKERS)
        for x, y in [(1.0, 1.0), (2.0, 2.0)]:
            s.data_points.add_data_point_for_scatter_series(x, y)
        s.marker.symbol = MarkerStyleType.DIAMOND
        s.marker.size = 14

        pres2 = tmp_pptx(pres)
        s2 = _first_chart(pres2).chart_data.series[0]
        assert s2.marker.symbol == MarkerStyleType.DIAMOND
        assert s2.marker.size == 14