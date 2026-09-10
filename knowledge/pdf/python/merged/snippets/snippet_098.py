def test_page_generate_appearances_counts_created():
    doc = _new_page_doc()
    page = doc.pages[0]
    page.annotations.add("Square", (0, 0, 50, 50), "")
    page.annotations.add("Circle", (60, 0, 110, 50), "")
    page.annotations.add("Sound", (0, 60, 20, 80), "")  # unsupported -> skipped
    assert page.annotations.generate_appearances() == 2