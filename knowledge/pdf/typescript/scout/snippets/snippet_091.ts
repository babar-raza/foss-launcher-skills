it('draws in ToSvg too', () => {
    const svg = Document.Open(note('/Name /Note /C [1 0 0]')).Pages[0].ToSvg();
    expect(svg).toContain('fill="#ff0000"');
  })