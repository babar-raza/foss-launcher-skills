import { Document } from '../src/document.js';

describe('Document', () => {
  it('opens a document', () => {
    const doc = Document.open('sample.pdf');
  });

  it('saves a document', () => {
    const doc = Document.open('sample.pdf');
    doc.save('out.pdf');
  });

  it('round-trips open then save', () => {
    const doc = Document.open('sample.pdf');
    doc.save('roundtrip.pdf');
  });
});
