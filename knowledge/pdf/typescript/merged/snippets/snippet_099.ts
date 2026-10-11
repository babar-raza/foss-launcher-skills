it('a /Text name on an attachment is unknown there', () => {
    expect(hash(attach('/Name /Note'))).toBe(hash(attach('/Name /PushPin')));
  })