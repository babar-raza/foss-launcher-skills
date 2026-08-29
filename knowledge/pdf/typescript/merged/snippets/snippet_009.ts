const doc = Document.OpenFile('in.pdf');
const page = doc.Pages[0];

// Page number, right-aligned near the bottom-right corner.
const w = page.Rect[2] - page.Rect[0];
page.AddText(`Page ${page.Number}`, w - 40, 20, { fontSize: 10, align: 'right' });

// Semi-transparent diagonal watermark, centered on the page.
page.AddText('DRAFT', page.Rect[2] / 2, page.Rect[3] / 2, {
  font: 'Times-Bold', fontSize: 64, color: [0.7, 0.7, 0.7], opacity: 0.4, rotate: 45, align: 'center',
});

doc.WriteTo('out.pdf');
