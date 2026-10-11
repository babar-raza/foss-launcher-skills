def test_major_gridlines_line_color(self):
        prs = Presentation()
        chart = prs.slides[0].shapes.add_chart(ChartType.CLUSTERED_COLUMN, 0, 0, 400, 300)
        gl = chart.axes.vertical_axis.major_grid_lines_format
        assert isinstance(gl, ChartLinesFormat)
        gl.line.fill_format.fill_type = FillType.SOLID
        gl.line.fill_format.solid_fill_color.color = Color.from_argb(255, 0, 0, 255)
        gl.line.width = 5

        prs2 = _save_and_reload(prs)
        chart2 = prs2.slides[0].shapes[0]
        gl2 = chart2.axes.vertical_axis.major_grid_lines_format
        assert gl2.line.fill_format.fill_type == FillType.SOLID
        assert gl2.line.fill_format.solid_fill_color.color.b == 255
        assert abs(gl2.line.width - 5) < 0.5