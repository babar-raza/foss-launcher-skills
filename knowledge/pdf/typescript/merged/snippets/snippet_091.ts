it('searches a HIDDEN annotation, unlike SearchAnnotations', () => {
    // The deliberate divergence. SearchAnnotations filters through
    // isAnnotVisible because it reports what a render DRAWS; this reports what
    // the file CARRIES, and a hidden annotation's text is still in the bytes —
    // and is still what redaction removes.
    const doc = noteDoc();
    doc.Pages[0].Annotations[0].Flags = 2;   // Hidden
    expect(doc.Pages[0].SearchAnnotationText('body secret')).toHaveLength(1);
  })