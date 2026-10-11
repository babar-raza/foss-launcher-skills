it('encodes SubmitForm with a URL filespec and no flags by default', () => {
    const d = encodeAction(blank(), { type: 'submit', url: 'https://example.com/post' });
    expect(nameOf(d.get('S'))).toBe('SubmitForm');
    const fs = d.get('F') as PdfDict;
    expect(isDict(fs)).toBe(true);
    expect(nameOf(fs.get('FS'))).toBe('URL');
    expect(str(fs.get('F'))).toBe('https://example.com/post');
    expect(d.has('Flags')).toBe(false);
    expect(d.has('Fields')).toBe(false);
  })