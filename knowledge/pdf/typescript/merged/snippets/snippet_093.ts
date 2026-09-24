it('rendering does not write an /AP into the document', () => {
    const d = Document.Open(note('/Name /Note'));
    d.Pages[0].ToImage();
    expect(d.Pages[0].Annotations[0].Dict.has('AP')).toBe(false);
  })