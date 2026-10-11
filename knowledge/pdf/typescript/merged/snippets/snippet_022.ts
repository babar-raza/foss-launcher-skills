function stampLogoOnEveryPage(doc: Document, skip: Page[]): void {
  const svg = asposeLogo();
  const skipNumbers = new Set(skip.map((p) => p.Number));
  const stampW = 120;
  const stampH = 38; // 314/100 * 38 ~= 119.3
  const margin = 25;

  for (const p of doc.Pages) {
    if (skipNumbers.has(p.Number)) continue;
    const urx = pageWidth(p) - margin;
    const ury = pageHeight(p) - margin;
    p.AddSVGObject(svg, xywh([urx - stampW, ury - stampH, urx, ury]));
  }
}