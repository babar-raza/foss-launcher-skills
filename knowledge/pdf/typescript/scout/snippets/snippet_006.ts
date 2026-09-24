import { Document } from '@asposefoss/pdf';
import { readFileSync, writeFileSync } from 'node:fs';

const doc = Document.Open(readFileSync('salvaged.pdf'));
if (doc.recovery) console.log('recovered:', doc.recovery.reason);

const report = doc.Validate();
for (const i of report.Issues) console.log(i.rule, i.object?.num, i.message);

if (!report.Passed) {
  const fixed = doc.Repair();
  console.log(`repaired ${fixed.length} issue(s)`);
  writeFileSync('repaired.pdf', doc.Save());
}
