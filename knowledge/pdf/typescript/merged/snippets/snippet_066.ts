it('now parses a submit action that previously read back as undefined', () => {
    const doc = Document.Open(buildClassicPdf(1));
    const link = doc.Pages[0].AddLink({
      rect: [10, 10, 100, 30],
      action: { type: 'submit', url: 'https://example.com/post', format: 'html' },
    });
    expect(link.Action).toEqual({
      type: 'submit', url: 'https://example.com/post', format: 'html',
    });
  })