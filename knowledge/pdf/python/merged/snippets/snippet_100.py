def test_flatten_matrix_maps_bbox_to_rect_without_double_scaling():
    doc = _new_page_doc()
    # Manual appearance authored in annot-local coords; BBox is [0 0 100 100].
    doc.pages[0].annotations.add(
        "Square",
        (100, 100, 200, 200),
        "",
        appearance_normal=b"0.5 g\n0 0 100 100 re f\n",
    )
    doc.flatten()
    content = doc._engine_pdf.page_contents[0]
    # BBox [0 0 100 100] -> Rect [100 100 200 200] is a pure translation, not the
    # old "[w 0 0 h x y]" double-scale.
    assert b"1 0 0 1 100 100 cm" in content
    assert b"100 0 0 100 100 100 cm" not in content