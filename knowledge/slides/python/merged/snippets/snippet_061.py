def test_text_format_latin_font(self):
        prs = Presentation()
        chart = prs.slides[0].shapes.add_chart(ChartType.CLUSTERED_COLUMN, 0, 0, 400, 300)
        pf = chart.axes.horizontal_axis.text_format.portion_format
        pf.latin_font = FontData("Arial")

        prs2 = _save_and_reload(prs)
        chart2 = prs2.slides[0].shapes[0]
        pf2 = chart2.axes.horizontal_axis.text_format.portion_format
        assert pf2.latin_font.font_name == "Arial"