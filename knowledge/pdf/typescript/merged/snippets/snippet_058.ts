it('encodes JavaScript', () => {
    const d = encodeAction(blank(), { type: 'javascript', script: 'app.alert(1)' });
    expect(nameOf(d.get('S'))).toBe('JavaScript');
    expect(str(d.get('JS'))).toBe('app.alert(1)');
  })