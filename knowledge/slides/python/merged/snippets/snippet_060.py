def test_text_format_color(self):
        prs = Presentation()
        chart = prs.slides[0].shapes.add_chart(ChartType.CLUSTERED_COLUMN, 0, 0, 400, 300)
        pf = chart.axes.vertical_axis.text_format.portion_format
        pf.fill_format.fill_type = FillType.SOLID
        pf.fill_format.solid_fill_color.color = Color.from_argb(255, 0, 100, 0)

        prs2 = _save_and_reload(prs)
        chart2 = prs2.slides[0].shapes[0]
        pf2 = chart2.axes.vertical_axis.text_format.portion_format
        assert pf2.fill_format.fill_type == FillType.SOLID
        assert pf2.fill_format.solid_fill_color.color.g == 100