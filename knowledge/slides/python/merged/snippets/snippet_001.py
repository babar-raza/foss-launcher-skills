def test_run_properties_keep_their_schema_order_however_they_were_set(
    produced, shape_on_blank_slide, order
):
    """`<a:rPr>` children follow `CT_TextCharacterProperties` for every permutation."""
    pres, shape = shape_on_blank_slide(with_text="Formatted")
    portion_format = shape.text_frame.paragraphs[0].portions[0].portion_format
    for operation in order:
        _apply(portion_format, operation)
    pkg = produced(pres)

    rpr = pkg.find_one(SLIDE, "//a:r/a:rPr")
    assert set(child_names(rpr)) >= {"a:latin", "a:highlight", "a:solidFill"}, (
        "the three formatting children were not all written: %r" % child_names(rpr)
    )
    pkg.assert_element(SLIDE, "//a:r/a:rPr", child_order=True)