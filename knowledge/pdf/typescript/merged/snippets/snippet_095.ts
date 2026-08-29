it('is disjoint from SearchAnnotations, in both directions', () => {
    const doc = Document.Open(buildAnnotTextPdf());
    const page = doc.Pages[0];
    // Object 6 is the /FreeText whose appearance draws "bravo".
    const freeText = page.Annotations.find((a) => a.Subtype === 'FreeText')!;
    freeText.Contents = 'carried';

    expect(page.SearchAnnotations('bravo')).toHaveLength(1);
    expect(page.SearchAnnotationText('bravo')).toHaveLength(0);

    expect(page.SearchAnnotationText('carried')).toHaveLength(1);
    expect(page.SearchAnnotations('carried')).toHaveLength(0);
  })