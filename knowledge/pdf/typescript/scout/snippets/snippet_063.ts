it('returns undefined with no /A, a non-dict /A, or an unmodelled /S', () => {
    const doc = blank();
    expect(parseAction(doc, new Map())).toBeUndefined();
    const named: PdfDict = new Map<string, PdfObject>([
      ['S', { kind: 'name', name: 'Named' } as PdfObject],
    ]);
    expect(parseAction(doc, annotWith(named))).toBeUndefined();
  })