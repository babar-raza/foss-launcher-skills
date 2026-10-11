import { Document } from '@asposefoss/pdf';
const doc = Document.OpenFile('in.pdf');
const svg = doc.Pages[0].ToSvg();          // standalone <svg> string
// fs.writeFileSync('page1.svg', svg);
const png = doc.Pages[0].ToImage({ scale: 2 }); // Uint8Array of PNG bytes @144 DPI
// fs.writeFileSync('page1.png', png);
const html = doc.ToHtml();                 // standalone semantic HTML, all pages
// fs.writeFileSync('out.html', html);
const md = doc.ToMarkdown();               // GFM Markdown, all pages
// fs.writeFileSync('out.md', md);
const docx = doc.ToDocx();                 // .docx bytes, reflowed, images in the package
// fs.writeFileSync('out.docx', docx);
const fixed = doc.ToDocx({ mode: 'textbox' });  // .docx keeping each page's own geometry
// fs.writeFileSync('fixed.docx', fixed);
