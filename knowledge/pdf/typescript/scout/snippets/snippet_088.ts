it('finds text in /Subj', () => {
    const hits = noteDoc().Pages[0].SearchAnnotationText('subject');
    expect(hits).toHaveLength(1);
    expect(hits[0].key).toBe('Subj');
  })