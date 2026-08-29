function sectionHeader(page: Page, title: string, subtitle = ''): void {
  const w = pageWidth(page);
  const h = pageHeight(page);
  addText(page, title, [50, h - 90, w - 50, h - 55], {
    font: 'Helvetica-Bold', size: 26, color: NAVY, align: 'center',
  });
  if (subtitle) {
    addText(page, subtitle, [50, h - 113, w - 50, h - 98], {
      font: 'Helvetica-Oblique', size: 11, color: MUTED, align: 'center',
    });
  }
}