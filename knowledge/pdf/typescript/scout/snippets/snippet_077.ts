it('leaves the straight border line empty at a scallop cusp', () => {
    expect(inkedAtBottomBorder(render(false), 160)).toBe(true);
    expect(inkedAtBottomBorder(render(true), 160)).toBe(false);
  })