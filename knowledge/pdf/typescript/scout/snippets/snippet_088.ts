it('an existing /AP wins over the icon', () => {
    const bytes = page(
      '<< /Type /Annot /Subtype /Text /Rect [50 50 150 150] /Name /Note /C [1 0 0] /AP << /N 5 0 R >> >>',
      ['<< /Type /XObject /Subtype /Form /BBox [0 0 100 100] /Length 0 >>\nstream\n\nendstream'],
    );
    expect(count(render(bytes), notWhite)).toBe(0);
  })