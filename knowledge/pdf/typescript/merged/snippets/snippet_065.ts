it('still round-trips a GoTo link', () => {
    const doc = Document.Open(buildClassicPdf(2));
    const link = doc.Pages[0].AddLink({
      rect: [10, 10, 100, 30], action: { type: 'goto', page: 2 },
    });
    expect(link.Action?.type).toBe('goto');
    expect((link.Action as { page: number }).page).toBe(2);
  })