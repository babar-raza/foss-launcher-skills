def test_axis_line_format(self):
        prs = Presentation()
        chart = prs.slides[0].shapes.add_chart(ChartType.CLUSTERED_COLUMN, 0, 0, 400, 300)
        fmt = chart.axes.vertical_axis.format
        assert isinstance(fmt, Format)
        fmt.line.fill_format.fill_type = FillType.SOLID
        fmt.line.fill_format.solid_fill_color.color = Color.from_argb(255, 255, 0, 0)
        fmt.line.width = 3

        prs2 = _save_and_reload(prs)
        chart2 = prs2.slides[0].shapes[0]
        fmt2 = chart2.axes.vertical_axis.format
        assert fmt2.line.fill_format.fill_type == FillType.SOLID
        assert fmt2.line.fill_format.solid_fill_color.color.r == 255
        assert abs(fmt2.line.width - 3) < 0.5