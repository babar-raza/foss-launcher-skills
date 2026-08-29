it('reports the REDUCED text as the match value, not the markup', () => {
    // `text` is a slice of `value`, so a markup `value` would index a string
    // the caller never saw and the offsets would be meaningless.
    const hits = rcDoc('<body><p>the report</p></body>').Pages[0]
      .SearchAnnotationText('report');
    expect(hits[0].value).toBe('the report');
    expect(hits[0].value).not.toContain('<');
  })