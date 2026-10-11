it('returns undefined for a /JS that is neither', () => {
    const doc = Document.New();
    const action = new Map<string, PdfObject>([['S', name('JavaScript')], ['JS', 42]]);
    expect(parseStandaloneAction(doc, action)).toBeUndefined();
  })