from aspose_core.document import Document


def test_open_and_save():
    doc = Document()
    doc.save('out.pdf')


def test_save_twice():
    doc = Document()
    doc.save('a.pdf')
    doc.save('b.pdf')
