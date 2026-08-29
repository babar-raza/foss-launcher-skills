import { Document, PageFormat } from '@asposefoss/pdf';

const doc = Document.New(PageFormat.A4);          // one blank A4 page
doc.Pages[0].AddText('Hello', 72, 720, { fontSize: 14 });
doc.AddPage(PageFormat.A4.landscape());           // append more as you go
doc.WriteTo('scratch.pdf');
