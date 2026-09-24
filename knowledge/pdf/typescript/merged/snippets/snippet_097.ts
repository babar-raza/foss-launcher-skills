it('every standard name reaches its own artwork', () => {
    const hashes = ATTACH_ICONS.map((n) => hash(attach(`/Name /${n}`)));
    expect(new Set(hashes).size).toBe(ATTACH_ICONS.length);
  })