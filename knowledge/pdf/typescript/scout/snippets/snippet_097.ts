it('does not match a tag name', () => {
    // The other half of the same defect: raw markup made every query for `p`,
    // `body` or `span` a hit on the syntax.
    expect(rcDoc('<body><p>the report</p></body>').Pages[0]
      .SearchAnnotationText('body')).toHaveLength(0);
  })