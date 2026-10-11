it('squares and centres the icon in a wide /Rect', () => {
    const img = decodePng(Document.Open(page(
      '<< /Type /Annot /Subtype /Text /Rect [0 50 200 150] /Name /Note /C [1 0 0] >>',
    )).Pages[0].ToImage());
    // A 100x100 square centred in a 200x100 rect spans x 50..150.
    expect(count(img, red, 0, 50, 45, 150)).toBe(0);
    expect(count(img, red, 155, 50, 200, 150)).toBe(0);
    expect(count(img, red, 50, 50, 150, 150)).toBeGreaterThan(1000);
  })