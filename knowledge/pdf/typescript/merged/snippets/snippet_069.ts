it('still reads a string /JS', () => {
    const doc = Document.New();
    const action = new Map<string, PdfObject>([
      ['S', name('JavaScript')],
      ['JS', { kind: 'string', bytes: encodePdfText('x = 1;') }],
    ]);
    expect(parseStandaloneAction(doc, action))
      .toEqual({ type: 'javascript', script: 'x = 1;' });
  })