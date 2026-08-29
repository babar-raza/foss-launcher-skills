function addUnifiedFooter(page: Page, index: number, total: number): void {
  const w = pageWidth(page);
  const g = page.Graphics();
  g.setStrokeColor([0.85, 0.85, 0.9]).setLineWidth(0.5)
    .drawLine(50, 40, w - 50, 40).stroke();
  g.apply();
  addText(page, `${DOC_TITLE}   ·   ${index} / ${total}`, [50, 22, w - 50, 36], {
    size: 8, color: [0.55, 0.55, 0.6], align: 'center',
  });
}