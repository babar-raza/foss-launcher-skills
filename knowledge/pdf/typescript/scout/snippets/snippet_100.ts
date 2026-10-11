it('draws a cloud border with no /AP, which regeneration alone could not', () => {
    // The half of v0tz.4 the regeneration path could not reach: /BE reached
    // ImportFdf/ImportXfdf but never a render of a document that simply
    // arrived without appearances.
    const be: PdfDict = new Map<string, PdfObject>([['S', name('C')], ['I', 2]]);
    const { doc, dict } = attach('Square', [
      ['Rect', [0, 0, 120, 80]], ['C', [1, 0, 0]], ['BE', be],
    ]);
    const body = fallbackBody(doc, dict);
    expect(body).toContain(' c\n');
    expect(body).not.toContain(' re');
  })