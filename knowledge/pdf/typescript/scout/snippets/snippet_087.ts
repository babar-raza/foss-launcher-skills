it('every standard name reaches its own artwork', () => {
    const hashes = TEXT_ICONS.map((n) => hash(note(`/Name /${n}`)));
    expect(new Set(hashes).size).toBe(TEXT_ICONS.length);
  })