it('a name from Object.prototype is unknown too, not a property lookup', () => {
    // A /Name comes out of the document, so `in` would find
    // Object.prototype.constructor here and draw nothing (predefcmap.ts's trap).
    expect(hash(note('/Name /constructor'))).toBe(hash(note('/Name /Note')));
  })