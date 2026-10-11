func ExampleDocument_Sign() {
	key, _ := ecdsa.GenerateKey(elliptic.P256(), cryptorand.Reader)
	tmpl := &x509.Certificate{
		SerialNumber: big.NewInt(1),
		Subject:      pkix.Name{CommonName: "Jane Signer"},
		NotBefore:    time.Now().Add(-time.Hour),
		NotAfter:     time.Now().Add(24 * time.Hour),
		KeyUsage:     x509.KeyUsageDigitalSignature,
	}
	der, _ := x509.CreateCertificate(cryptorand.Reader, tmpl, tmpl, &key.PublicKey, key)
	cert, _ := x509.ParseCertificate(der)

	doc := pdf.NewDocumentFromFormat(pdf.PageFormatA4)
	if err := doc.Sign(pdf.SignOptions{Certificate: cert, PrivateKey: key, Reason: "Approval"}); err != nil {
		log.Fatal(err)
	}
	var buf bytes.Buffer
	if _, err := doc.WriteTo(&buf); err != nil {
		log.Fatal(err)
	}

	signed, _ := pdf.OpenStream(&buf)
	sigs, err := signed.VerifySignatures()
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("signatures: %d, valid: %v, reason: %s\n", len(sigs), sigs[0].Valid, sigs[0].Reason)
	// Output: signatures: 1, valid: true, reason: Approval
}