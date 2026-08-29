it('still round-trips a URI link', () => {
    const doc = Document.Open(buildClassicPdf(1));
    const link = doc.Pages[0].AddLink({
      rect: [10, 10, 100, 30], action: { type: 'uri', uri: 'https://example.com' },
    });
    expect(link.Action).toEqual({ type: 'uri', uri: 'https://example.com' });
  })