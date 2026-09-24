it('only /Text and /FileAttachment get an icon: a /Link with no /AP stays blank', () => {
    // /Name /PushPin is a real icon name, so a build that dropped the subtype
    // gate would find artwork for it and draw.
    //
    // The subtype here was a /Square until kapw, which gave every shape and
    // text-markup subtype a no-/AP fallback of its own — so a /Square is no
    // longer blank, and proves nothing about the ICON gate. A /Link has no
    // visual at all and is what is left.
    const bytes = page('<< /Type /Annot /Subtype /Link /Rect [50 50 150 150] /Name /PushPin >>');
    expect(count(render(bytes), notWhite)).toBe(0);
  })