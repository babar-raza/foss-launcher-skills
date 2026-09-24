it('still reaches that line at a scallop peak', () => {
    // Without this the case above passes for a cloud that is merely missing,
    // or drawn too small to touch the border at all.
    expect(inkedAtBottomBorder(render(true), 135)).toBe(true);
  })