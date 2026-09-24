import { Document, LoadLimits, ResourceLimitError, PdfParseError } from '@asposefoss/pdf';

// Tighter than the defaults for an upload endpoint; null disables one field alone.
const limits = LoadLimits.defaults.with({ maxFileBytes: 50 * 1024 * 1024, maxImagePixels: 1 << 26 });

try {
  const doc = Document.OpenFile('upload.pdf', { limits });
  console.log(doc.Pages[0].GetText());
} catch (e) {
  if (e instanceof ResourceLimitError) console.error(`refused: ${e.limit} (allowed ${e.allowed}, reached ${e.reached})`);
  else if (e instanceof PdfParseError) console.error('not a readable PDF');
  else throw e;
}

// Input you produced yourself can opt out explicitly.
const trusted = Document.OpenFile('our-own-report.pdf', { limits: LoadLimits.unlimited() });
