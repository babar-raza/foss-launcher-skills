it('keeps rejecting a malformed link action', () => {
    const doc = Document.Open(buildClassicPdf(1));
    expect(() => doc.Pages[0].AddLink({
      rect: [10, 10, 100, 30], action: { type: 'goto', page: 99 },
    })).toThrow(RangeError);
    expect(() => doc.Pages[0].AddLink({
      rect: [10, 10, 100, 30], action: { type: 'bogus' } as never,
    })).toThrow(TypeError);
  })