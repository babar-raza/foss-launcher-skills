def test_bubble_size_scale_round_trip(self, tmp_pptx):
        """bubble_size_scale persists across save/reload."""
        pres = Presentation()
        chart = _add_clean_chart(pres, ChartType.BUBBLE)
        s = chart.chart_data.series.add("B", ChartType.BUBBLE)
        for x, y, sz in [(1.0, 1.0, 10), (2.0, 2.0, 20)]:
            s.data_points.add_data_point_for_bubble_series(x, y, sz)
        chart.chart_data.series_groups[0].bubble_size_scale = 200

        pres2 = tmp_pptx(pres)
        grp = _first_chart(pres2).chart_data.series_groups[0]
        assert grp.bubble_size_scale == 200