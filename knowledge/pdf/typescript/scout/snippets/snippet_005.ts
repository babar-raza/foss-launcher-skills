const doc = Document.OpenFile('in.pdf');
doc.WriteTo('locked.pdf', {
  encrypt: {
    userPassword: 'open-me',       // required to open (default '')
    ownerPassword: 'full-rights',  // default: same as userPassword
    algorithm: 'aes256',           // 'aes256' (default) | 'aes128' | 'rc4'
    permissions: { copying: false, modifying: false },
    encryptMetadata: true,
  },
});
