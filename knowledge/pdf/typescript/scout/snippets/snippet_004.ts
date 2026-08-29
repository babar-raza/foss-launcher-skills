import { Document, InvalidPasswordError } from '@asposefoss/pdf';

try {
  const doc = Document.OpenFile('secret.pdf', { password: 'hunter2' });
  doc.WriteTo('decrypted.pdf');    // output is plaintext
} catch (e) {
  if (e instanceof InvalidPasswordError) console.error('wrong password');
  else throw e;
}
