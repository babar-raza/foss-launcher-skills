it('rejects malformed actions', () => {
    const doc = blank();
    expect(() => encodeAction(doc, { type: 'uri', uri: '' })).toThrow(TypeError);
    expect(() => encodeAction(doc, { type: 'submit', url: '' })).toThrow(TypeError);
    expect(() => encodeAction(doc, { type: 'javascript', script: '' })).toThrow(TypeError);
    expect(() => encodeAction(doc, { type: 'goto', page: 9 })).toThrow(RangeError);
    expect(() => encodeAction(doc, { type: 'goto', page: 0 })).toThrow(RangeError);
    expect(() => encodeAction(doc, {
      type: 'submit', url: 'u', fields: [1] as never,
    })).toThrow(TypeError);
    expect(() => encodeAction(doc, { type: 'nope' } as never)).toThrow(TypeError);
  })