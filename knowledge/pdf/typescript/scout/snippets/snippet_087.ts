it('finds text in /T, which a /Contents-only search would miss', () => {
    // The reason this earns an API: test/redact-annots.test.ts already treats
    // an author name as a secret redaction must remove, so a search that
    // reported "not found" for it would contradict the same document's redact.
    const hits = noteDoc().Pages[0].SearchAnnotationText('Lovelace');
    expect(hits).toHaveLength(1);
    expect(hits[0].key).toBe('T');
    expect(hits[0].value).toBe('Ada Lovelace');
  })