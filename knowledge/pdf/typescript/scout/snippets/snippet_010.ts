import { parseContentStream, serializeContentStream } from '@asposefoss/pdf';

const ops = parseContentStream(doc.Pages[0].Contents);
// ops: { operator: string, operands: PdfObject[], inlineImage?: {...} }[]
for (const op of ops) {
  if (op.operator === 'Tj') console.log('text op:', op.operands);
}
const bytes = serializeContentStream(ops);       // round-trips operators + operands
