def test_add_bubble_data_points(self):
        """X/Y/Size values accessible on bubble data points after adding."""
        pres = Presentation()
        chart = _add_clean_chart(pres, ChartType.BUBBLE)
        s = chart.chart_data.series.add("B", ChartType.BUBBLE)
        pts = [(1.0, 2.0, 5), (3.0, 4.0, 15), (5.0, 6.0, 25)]
        for x, y, sz in pts:
            s.data_points.add_data_point_for_bubble_series(x, y, sz)

        for dp, (x, y, sz) in zip(s.data_points, pts):
            assert dp.x_value.as_literal_double == x
            assert dp.y_value.as_literal_double == y
            assert dp.bubble_size.as_literal_double == sz