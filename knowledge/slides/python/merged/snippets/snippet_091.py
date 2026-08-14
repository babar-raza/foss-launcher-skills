def test_scatter_emits_xVal_and_yVal(self, tmp_path):
        pres = Presentation()
        chart = _add_clean_chart(pres, ChartType.SCATTER_WITH_MARKERS)
        s = chart.chart_data.series.add("S", ChartType.SCATTER_WITH_MARKERS)
        s.data_points.add_data_point_for_scatter_series(1.0, 2.0)
        s.data_points.add_data_point_for_scatter_series(3.0, 4.0)

        xml = self._save_and_read_chart_xml(pres, tmp_path)
        assert '<c:xVal>' in xml
        assert '<c:yVal>' in xml
        assert '<c:val>' not in xml  # scatter must not use <c:val>