it('applies a RegExp globally within one value', () => {
    const doc = Document.Open(buildMultiStreamPage(['BT /F1 10 Tf 50 100 Td (x) Tj ET']));
    doc.Pages[0].AddTextNote({ rect: [60, 90, 80, 110], contents: 'a1 b2 c3' });
    const hits = doc.Pages[0].SearchAnnotationText(/[a-c]\d/);
    expect(hits.map((h) => h.text)).toEqual(['a1', 'b2', 'c3']);
    expect(hits.every((h) => h.key === 'Contents')).toBe(true);
  })