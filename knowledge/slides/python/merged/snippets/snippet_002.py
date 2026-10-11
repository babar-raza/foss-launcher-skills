def test_run_properties_come_before_the_run_text(produced, shape_on_blank_slide):
    """`CT_RegularTextRun` is `rPr?` then `t`; formatting after the text is discarded."""
    pres, shape = shape_on_blank_slide(with_text="Formatted")
    shape.text_frame.paragraphs[0].portions[0].portion_format.font_height = 24.0
    pkg = produced(pres)

    pkg.assert_element(SLIDE, "//a:p/a:r", child_order=True)