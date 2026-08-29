it('does not search page content', () => {
    expect(noteDoc().Pages[0].SearchAnnotationText('page')).toHaveLength(0);
  })