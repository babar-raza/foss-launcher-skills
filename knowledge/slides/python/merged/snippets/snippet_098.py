def test_scatter_via_workbook_cells(self, tmp_pptx):
        pres = Presentation()
        chart = _add_clean_chart(pres, ChartType.SCATTER_WITH_MARKERS)
        wb = chart.chart_data.chart_data_workbook
        name_cell = wb.get_cell(0, "B1", "Data")
        s = chart.chart_data.series.add(name_cell, ChartType.SCATTER_WITH_MARKERS)
        expected = [(1.0, 2.5), (2.5, 4.1), (4.2, 3.3)]
        for i, (x, y) in enumerate(expected):
            row = i + 2
            x_cell = wb.get_cell(0, f"A{row}", x)
            y_cell = wb.get_cell(0, f"B{row}", y)
            s.data_points.add_data_point_for_scatter_series(x_cell, y_cell)

        pres2 = tmp_pptx(pres)
        s2 = _first_chart(pres2).chart_data.series[0]
        for dp, (x, y) in zip(s2.data_points, expected):
            assert dp.x_value.as_literal_double == pytest.approx(x)
            assert dp.y_value.as_literal_double == pytest.approx(y)