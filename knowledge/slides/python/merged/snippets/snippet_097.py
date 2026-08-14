def test_smooth_line_scatter_emits_smooth_val_1(self, tmp_path):
        pres = Presentation()
        chart = _add_clean_chart(pres, ChartType.SCATTER_WITH_SMOOTH_LINES)
        s = chart.chart_data.series.add(
            "S", ChartType.SCATTER_WITH_SMOOTH_LINES)
        s.data_points.add_data_point_for_scatter_series(1.0, 1.0)
        s.data_points.add_data_point_for_scatter_series(2.0, 2.0)

        xml = self._save_and_read_chart_xml(pres, tmp_path)
        assert '<c:smooth val="1"/>' in xml