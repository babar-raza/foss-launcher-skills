it('survives FlattenAnnotations as page content', () => {
    const d = Document.Open(note('/Name /Note /C [1 0 0]'));
    d.FlattenAnnotations();
    const re = Document.Open(d.Save());
    expect(re.Pages[0].Annotations.length).toBe(0);
    expect(count(decodePng(re.Pages[0].ToImage()), red, 50, 50, 150, 150)).toBeGreaterThan(1000);
  })