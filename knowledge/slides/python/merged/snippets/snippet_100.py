def test_3d_bubble_adds_bubble3D_val_1_via_chart_type(self, tmp_path):
        """End-to-end: when a chart is created as BUBBLE_WITH_3D and a series
        is added with chart.type, the series emits <c:bubble3D val="1"/>.
        """
        import zipfile
        from aspose.slides_foss.export import SaveFormat

        pres = Presentation()
        chart = pres.slides[0].shapes.add_chart(
            ChartType.BUBBLE_WITH_3D, 50, 50, 500, 400, False)
        chart.chart_data.series.clear()
        s = chart.chart_data.series.add("S", chart.type)
        s.data_points.add_data_point_for_bubble_series(1.0, 2.0, 10)

        path = str(tmp_path / "x.pptx")
        pres.save(path, SaveFormat.PPTX)
        with zipfile.ZipFile(path) as z:
            xml = z.read('ppt/charts/chart1.xml').decode()
        assert '<c:bubble3D val="1"/>' in xml
        assert '<c:bubble3D val="0"/>' not in xml