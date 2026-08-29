async function verifySignedDocument(path: string): Promise<void> {
  console.log('verifying signed sibling:');
  check(existsSync(path), `${path} was written`);
  const doc = Document.OpenFile(path);
  const reports = await doc.VerifySignatures();
  check(reports.length === 2, `the sibling carries two signatures (${reports.length})`);
  reports.forEach((r, i) => {
    check(r.integrity === 'valid',
      `signature ${i + 1} (${r.name}) has an intact /ByteRange digest`);
    check(r.signature === 'valid',
      `signature ${i + 1} (${r.name}) verifies cryptographically`);
  });
  // By name, not by index: the two differ in exactly the way that proves the
  // append happened, and an index-based check would not notice them swapping.
  const cert = reports.find((r) => r.name === 'ShowcaseCertification');
  const approval = reports.find((r) => r.name === 'ShowcaseApproval');
  check(cert !== undefined && approval !== undefined,
    'both signature fields are present by name');
  check(cert!.docMDP === 'ok', "the certification's DocMDP verdict is ok");
  check(approval!.coversWholeFile,
    'the approval signature covers the whole file');
  // The certification was signed before the approval was appended, so its
  // /ByteRange stops short of the end. That asymmetry IS the incremental
  // append: were the second signature a full rewrite, the first would be gone.
  check(!cert!.coversWholeFile,
    'the certification does not cover the appended revision (proving the append)');

  // The unsigned document outlines SIGNATURE_RECT and promises the signature
  // lands there, so the two must actually agree.
  const signingPage = destPage(doc, 'section.signing');
  const widget = signingPage.Annotations.find((a) => a.Subtype === 'Widget');
  check(widget !== undefined, 'the visible signature widget is on the signing page');
  const rect = widget?.Rect?.map(Math.round) ?? [];
  check(JSON.stringify(rect) === JSON.stringify(SIGNATURE_RECT),
    `the widget occupies the advertised rect ${JSON.stringify(SIGNATURE_RECT)}`);

  console.log('signed sibling verified');
}