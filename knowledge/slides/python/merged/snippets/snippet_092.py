def test_bubble_emits_xVal_yVal_bubbleSize(self, tmp_path):
        pres = Presentation()
        chart = _add_clean_chart(pres, ChartType.BUBBLE)
        s = chart.chart_data.series.add("B", ChartType.BUBBLE)
        s.data_points.add_data_point_for_bubble_series(1.0, 2.0, 10)
        s.data_points.add_data_point_for_bubble_series(3.0, 4.0, 20)

        xml = self._save_and_read_chart_xml(pres, tmp_path)
        assert '<c:xVal>' in xml
        assert '<c:yVal>' in xml
        assert '<c:bubbleSize>' in xml