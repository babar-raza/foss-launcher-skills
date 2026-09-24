import { Document } from '@asposefoss/pdf';

// Encrypt to one or more recipient certificates (PEM string or DER bytes):
const bytes = doc.Save({
  encrypt: {
    recipients: [{ certificate: recipientCertPem }],
    algorithm: 'aes256',                 // 'aes256' (default) | 'aes128' | 'rc4'
    permissions: { copying: false },     // shared across all recipients
  },
});

// Open with the recipient's private key + certificate, or a PKCS#12 bundle:
const opened = Document.Open(bytes, {
  recipient: { privateKey, certificate: recipientCertPem },
  // or: recipient: { pkcs12: p12Bytes, passphrase: '…' },
});
console.log(opened.Permissions);         // recovered permission flags (not enforced)
