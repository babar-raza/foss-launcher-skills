it('maps each submit format to its specification flag bit', () => {
    const doc = blank();
    const flagsFor = (format: 'fdf' | 'html' | 'xfdf' | 'pdf') =>
      encodeAction(doc, { type: 'submit', url: 'u', format }).get('Flags');
    expect(flagsFor('fdf')).toBeUndefined();   // no bit set
    expect(flagsFor('html')).toBe(4);          // bit 3, ExportFormat
    expect(flagsFor('xfdf')).toBe(32);         // bit 6, XFDF
    expect(flagsFor('pdf')).toBe(256);         // bit 9, SubmitPDF
  })