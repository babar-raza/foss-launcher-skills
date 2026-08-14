def test_straight_line_scatter_emits_smooth_val_0(self, tmp_path):
        """Straight-line scatter must explicitly set <c:smooth val="0"/>,
        otherwise PowerPoint defaults the line to smoothed."""
        pres = Presentation()
        chart = _add_clean_chart(pres, ChartType.SCATTER_WITH_STRAIGHT_LINES)
        s = chart.chart_data.series.add(
            "L", ChartType.SCATTER_WITH_STRAIGHT_LINES)
        s.data_points.add_data_point_for_scatter_series(1.0, 1.0)
        s.data_points.add_data_point_for_scatter_series(2.0, 2.0)

        xml = self._save_and_read_chart_xml(pres, tmp_path)
        assert '<c:smooth val="0"/>' in xml
        assert '<c:smooth val="1"/>' not in xml