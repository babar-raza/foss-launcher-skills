it('reads a stream /JS, not just a string', () => {
    // 32000-1 table 217: /JS is a text string OR a text stream, and a large
    // script is commonly the stream form. Before this, isString was the only
    // branch, so the WHOLE action read back as undefined — not merely its
    // script.
    const doc = Document.New();
    const js = doc.allocObject({
      kind: 'stream', dict: new Map(), raw: enc('app.alert("hi");'),
    });
    const action = new Map<string, PdfObject>([['S', name('JavaScript')], ['JS', js]]);
    expect(parseStandaloneAction(doc, action))
      .toEqual({ type: 'javascript', script: 'app.alert("hi");' });
  })