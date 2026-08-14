def test_3d_bubble_emits_bubble3D_in_ser(self, tmp_path):
        """<c:bubble3D val="1"/> must live inside <c:ser>, not at chart-type level.

        Regression: old code put bubble3D directly under <c:bubbleChart>, which
        corrupted the file in PowerPoint.
        """
        pres = Presentation()
        chart = _add_clean_chart(pres, ChartType.BUBBLE_WITH_3D)
        s = chart.chart_data.series.add("B3", ChartType.BUBBLE_WITH_3D)
        s.data_points.add_data_point_for_bubble_series(1.0, 2.0, 10)

        xml = self._save_and_read_chart_xml(pres, tmp_path)
        # bubble3D should appear inside <c:ser>, right after </c:bubbleSize>
        ser_block = xml.split('<c:ser>')[1].split('</c:ser>')[0]
        assert '<c:bubble3D val="1"/>' in ser_block
        # and should NOT appear outside the ser as a direct child of bubbleChart
        chart_block = xml.split('<c:bubbleChart>')[1].split('<c:ser>')[0]
        assert 'bubble3D' not in chart_block