it('finds text in /Contents and names the entry', () => {
    const hits = noteDoc().Pages[0].SearchAnnotationText('body secret');
    expect(hits).toHaveLength(1);
    expect(hits[0].key).toBe('Contents');
    expect(hits[0].value).toBe('body secret');
    expect(hits[0].text).toBe('body secret');
  })