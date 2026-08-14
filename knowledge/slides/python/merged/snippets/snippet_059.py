def test_value_axis_text_bold_italic(self):
        prs = Presentation()
        chart = prs.slides[0].shapes.add_chart(ChartType.CLUSTERED_COLUMN, 0, 0, 400, 300)
        tf = chart.axes.vertical_axis.text_format
        assert isinstance(tf, ChartTextFormat)
        pf = tf.portion_format
        assert isinstance(pf, ChartPortionFormat)
        pf.font_bold = NullableBool.TRUE
        pf.font_italic = NullableBool.TRUE
        pf.font_height = 16

        prs2 = _save_and_reload(prs)
        chart2 = prs2.slides[0].shapes[0]
        pf2 = chart2.axes.vertical_axis.text_format.portion_format
        assert pf2.font_bold == NullableBool.TRUE
        assert pf2.font_italic == NullableBool.TRUE
        assert abs(pf2.font_height - 16) < 0.5