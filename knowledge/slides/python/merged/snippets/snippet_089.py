def test_bubble_3d_round_trip(self, tmp_pptx):
        """BUBBLE_WITH_3D preserves X/Y/size."""
        pres = Presentation()
        chart = _add_clean_chart(pres, ChartType.BUBBLE_WITH_3D)
        s = chart.chart_data.series.add("B3", ChartType.BUBBLE_WITH_3D)
        for x, y, sz in [(1.0, 3.0, 10), (2.0, 6.0, 25)]:
            s.data_points.add_data_point_for_bubble_series(x, y, sz)

        pres2 = tmp_pptx(pres)
        s2 = _first_chart(pres2).chart_data.series[0]
        assert len(s2.data_points) == 2
        assert s2.data_points[1].bubble_size.as_literal_double == pytest.approx(25)