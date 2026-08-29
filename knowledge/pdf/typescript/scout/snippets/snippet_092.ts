it('returns [] for a page with no annotations', () => {
    const doc = Document.Open(buildMultiStreamPage(['BT /F1 10 Tf 50 100 Td (x) Tj ET']));
    expect(doc.Pages[0].SearchAnnotationText('anything')).toHaveLength(0);
  })