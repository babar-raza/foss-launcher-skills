function addSigningShowcase(page: Page): void {
  const w = pageWidth(page);

  sectionHeader(page, 'Digital Signatures',
    'certification with DocMDP  •  an approval signature  •  incremental append  •  verification');

  addText(page,
    'This document is deliberately left unsigned — signing would freeze it '
    + 'against the regeneration this example exists to perform. Instead the run '
    + 're-opens the finished PDF and writes a signed sibling: first a '
    + 'certification (author) signature carrying a DocMDP transform that permits '
    + 'form filling and nothing more, then a second approval signature over the '
    + 'result.',
    [50, 620, w - 50, 700], { size: 10, color: INK, lineSpacing: 1.35 });

  addText(page,
    'Two signatures rather than one, because the second is what exercises the '
    + "incremental-append path: the first signature's bytes must survive "
    + 'verbatim underneath it, and a single signature would not distinguish an '
    + 'append from a full rewrite. Credentials are minted on every run — an '
    + "RSA-2048 keypair and a self-signed certificate built with the library's "
    + 'own DER encoder — so there is nothing checked in and nothing to expire.',
    [50, 548, w - 50, 612], { size: 10, color: INK, lineSpacing: 1.35 });

  // The placeholder outline: the same rect the certification occupies in the
  // sibling, drawn here so the two can be compared side by side.
  const g = page.Graphics();
  g.save().setStrokeColor([0.70, 0.72, 0.82]).setLineWidth(1).setDash([5, 4])
    .rect(SIGNATURE_RECT[0], SIGNATURE_RECT[1],
      SIGNATURE_RECT[2] - SIGNATURE_RECT[0], SIGNATURE_RECT[3] - SIGNATURE_RECT[1])
    .stroke().restore();
  g.apply();

  addText(page, 'Signature appears here in the signed sibling',
    [SIGNATURE_RECT[0] + 10, SIGNATURE_RECT[1] + 40,
      SIGNATURE_RECT[2] - 10, SIGNATURE_RECT[1] + 62],
    { size: 9.5, color: MUTED, align: 'center' });

  addText(page,
    'Open docs/feature-showcase-signed.pdf to see it filled. A viewer will '
    + 'report both signatures as cryptographically valid but untrusted — the '
    + 'certificates are self-signed, so there is no trust anchor to chain to. '
    + "This run's console output lists each signature's signer, integrity, "
    + 'byte-range coverage and DocMDP verdict.',
    [SIGNATURE_RECT[2] + 24, 436, w - 50, 528],
    { size: 9, color: MUTED, lineSpacing: 1.35 });

  void NAVY;
}