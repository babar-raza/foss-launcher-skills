it('does not join two blocks into a word that was never written', () => {
    expect(rcDoc('<p>a</p><p>b</p>').Pages[0].SearchAnnotationText('ab')).toHaveLength(0);
    expect(rcDoc('<p>a</p><p>b</p>').Pages[0].SearchAnnotationText('a')).toHaveLength(1);
  })