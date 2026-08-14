// Sign — pass your own certificate + key (crypto.Signer: RSA or ECDSA).
// Here a self-signed test pair is generated in memory; in production load
// your key+cert from PEM (crypto/x509) or an HSM.
key, _ := rsa.GenerateKey(rand.Reader, 2048)
tmpl := x509.Certificate{
    SerialNumber: big.NewInt(1),
    Subject:      pkix.Name{CommonName: "Jane Doe"},
    NotBefore:    time.Now(), NotAfter: time.Now().AddDate(1, 0, 0),
    KeyUsage:     x509.KeyUsageDigitalSignature,
}
der, _ := x509.CreateCertificate(rand.Reader, &tmpl, &tmpl, &key.PublicKey, key)
cert, _ := x509.ParseCertificate(der)

doc := pdf.NewDocument(595, 842)
doc.Sign(pdf.SignOptions{
    Certificate: cert,
    PrivateKey:  key, // *rsa.PrivateKey and *ecdsa.PrivateKey both satisfy crypto.Signer
    Reason:      "I approve this document",
    Name:        "Jane Doe",
    // Optional: draw a visible "Digitally signed by …" block on the page.
    Visible: true,
    Rect:    pdf.Rectangle{LLX: 60, LLY: 60, URX: 360, URY: 140},
    // Page: 1 (default); Appearance: customize text/style à la SignatureCustomAppearance.
    // Optional standards extras:
    PAdES:        true,                             // ETSI.CAdES.detached (PAdES baseline)
    Certify:      pdf.CertifyFillForms,             // certification (DocMDP) signature
    TimestampURL: "http://timestamp.digicert.com",  // RFC 3161 trusted timestamp (needs network)
})
doc.Save("signed.pdf") // signature is computed and spliced in on Save

// Verify
signed, _ := pdf.Open("signed.pdf")
sigs, _ := signed.VerifySignatures()
for _, s := range sigs {
    fmt.Printf("%s: valid=%v intact=%v whole-doc=%v signer=%s\n",
        s.FieldName, s.Valid, s.IntegrityOK, s.CoversWholeDocument,
        s.Certificate.Subject.CommonName)
}
