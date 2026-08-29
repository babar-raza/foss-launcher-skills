it('carries no geometry — a hit must not be feedable to Redact', () => {
    // (a)'s only available geometry is the whole /Rect, which is exactly the
    // shape the c3t7.6 design refused: redacting it burns a box over whatever
    // else sits under the annotation.
    const hit = noteDoc().Pages[0].SearchAnnotationText('body secret')[0];
    expect(Object.keys(hit).sort()).toEqual(['annot', 'key', 'text', 'value']);
  })