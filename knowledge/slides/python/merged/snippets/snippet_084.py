def test_scatter_has_no_categories_path(self):
        """When data points supply X values, categories are not emitted to xVal."""
        import zipfile, tempfile, os
        from aspose.slides_foss.export import SaveFormat

        pres = Presentation()
        chart = _add_clean_chart(pres, ChartType.SCATTER_WITH_MARKERS)
        s = chart.chart_data.series.add("S", ChartType.SCATTER_WITH_MARKERS)
        for x, y in [(1.0, 10.0), (2.0, 20.0)]:
            s.data_points.add_data_point_for_scatter_series(x, y)

        fd, path = tempfile.mkstemp(suffix='.pptx')
        os.close(fd)
        try:
            pres.save(path, SaveFormat.PPTX)
            with zipfile.ZipFile(path) as z:
                xml = z.read('ppt/charts/chart1.xml').decode()
        finally:
            os.unlink(path)

        # xVal should use numRef (numeric) not strRef (string categories)
        assert '<c:xVal>' in xml
        xval_block = xml.split('<c:xVal>')[1].split('</c:xVal>')[0]
        assert '<c:numRef>' in xval_block
        assert '<c:strRef>' not in xval_block