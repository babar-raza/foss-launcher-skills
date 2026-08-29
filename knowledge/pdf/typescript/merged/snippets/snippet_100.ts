it('reads the stream shape as well as the string shape', () => {
    // /RC carries the same string-or-stream duality a field's /RV does, and
    // Acrobat writes a stream for anything sizeable.
    const doc = Document.Open(buildMultiStreamPage(['BT /F1 10 Tf 50 100 Td (page) Tj ET']));
    const note = doc.Pages[0].AddTextNote({ rect: [60, 90, 80, 110], contents: 'zzz' });
    const markup = '<body><p>streamed richness</p></body>';
    note.Dict.set('RC', {
      kind: 'stream',
      dict: new Map<string, PdfObject>([['Length', markup.length]]),
      raw: new TextEncoder().encode(markup),
    });
    expect(doc.Pages[0].SearchAnnotationText('streamed richness')).toHaveLength(1);
  })