it('accepts a bare string /F, which some producers write', () => {
    const doc = blank();
    const a: PdfDict = new Map<string, PdfObject>([
      ['S', { kind: 'name', name: 'SubmitForm' } as PdfObject],
      ['F', { kind: 'string', bytes: new TextEncoder().encode('https://bare') }],
    ]);
    expect(parseAction(doc, annotWith(a))).toEqual({
      type: 'submit', url: 'https://bare', format: 'fdf',
    });
  })