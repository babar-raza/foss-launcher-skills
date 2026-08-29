function mintSigner(commonName: string): MintedSigner {
  const { privateKey, publicKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });
  const certAlgId = der.sequence(der.oid(SHA256_WITH_RSA), der.null_());
  const spki = new Uint8Array(publicKey.export({ format: 'der', type: 'spki' }));

  const tbs = der.sequence(
    der.explicit(0, der.integer(2)),                       // version v3
    der.integer(BigInt(Date.now())),                       // serialNumber
    certAlgId,                                             // signature
    name(commonName),                                      // issuer
    der.sequence(
      der.utcTime(new Date(Date.UTC(2020, 0, 1))),
      der.utcTime(new Date(Date.UTC(2049, 11, 31))),
    ),                                                     // validity
    name(commonName),                                      // subject (self-signed)
    spki,                                                  // subjectPublicKeyInfo
  );

  const sig = new Uint8Array(cryptoSign('sha256', tbs, privateKey));
  const certificate = der.sequence(tbs, certAlgId, der.bitString(sig));
  return { certificate, privateKey, commonName };
}