it('reports every entry that matches, in Contents/T/Subj order', () => {
    const doc = Document.Open(buildMultiStreamPage(['BT /F1 10 Tf 50 100 Td (x) Tj ET']));
    const n = doc.Pages[0].AddTextNote({ rect: [60, 90, 80, 110], contents: 'zed', author: 'zed' });
    n.Dict.set('Subj', str('zed'));
    expect(doc.Pages[0].SearchAnnotationText('zed').map((h) => h.key))
      .toEqual(['Contents', 'T', 'Subj']);
  })