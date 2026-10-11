async function signSavedDocument(
  sourcePath: string, signaturePageIndex: number,
): Promise<void> {
  const author = mintSigner('Aspose Showcase Author');
  const approver = mintSigner('Aspose Showcase Approver');

  // Pass 1 — certification, over the whole file.
  const certifying = Document.OpenFile(sourcePath);
  await certifying.Certify(
    { certificate: author.certificate, privateKey: author.privateKey },
    {
      permissions: 'form-fill',
      reason: 'Certifying the feature showcase',
      location: 'Prague, CZ',
      name: author.commonName,
      fieldName: 'ShowcaseCertification',
      appearance: {
        page: signaturePageIndex,
        rect: SIGNATURE_RECT,
        text: `Certified by ${author.commonName}\n`
          + 'DocMDP: form filling permitted\n'
          + 'Aspose.PDF FOSS for TypeScript',
      },
    },
  );

  const certifiedBytes = certifying.Save();

  // Pass 2 — approval, appended incrementally onto those finished bytes. The
  // certification's byte range must survive verbatim underneath it.
  const approving = Document.Open(certifiedBytes);
  await approving.Sign(
    { certificate: approver.certificate, privateKey: approver.privateKey },
    {
      reason: 'Approved for publication',
      name: approver.commonName,
      fieldName: 'ShowcaseApproval',
      subFilter: 'PAdES',
    },
  );

  approving.WriteTo(SIGNED_PATH);
  console.log(`signed: ${SIGNED_PATH} `
    + `(certified ${(certifiedBytes.length / 1024).toFixed(1)} KB, then appended)`);

  const reports = await Document.OpenFile(SIGNED_PATH).VerifySignatures();
  for (const r of reports) {
    console.log(`  ${r.name}: signer=${r.signerCert?.subject ?? '(unparsed)'} `
      + `integrity=${r.integrity} signature=${r.signature} `
      + `coversWholeFile=${r.coversWholeFile} docMDP=${r.docMDP}`);
  }
}