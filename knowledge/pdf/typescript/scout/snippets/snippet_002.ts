import { Document } from '@asposefoss/pdf';

// Open from disk (or Document.Open(uint8array) for in-memory data)
const doc = Document.OpenFile('input.pdf');

// Inspect and edit pages
console.log(doc.Pages.length);
doc.Pages[0].Rotate = 90;
doc.RemovePage(2);                 // 1-based page number
doc.Reorder([3, 1, 2]);

// Metadata
doc.SetMetadata({ title: 'Report', author: 'Jane', custom: { Dept: 'R&D' } });

// Save
doc.WriteTo('output.pdf');         // or: const bytes = doc.Save();
doc.WriteTo('small.pdf', { compressed: true }); // xref stream + object streams
