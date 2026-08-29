function addCenteredWatermark(doc: Document, page: Page, text: string): void {
  doc.AddWatermark({
    text,
    pages: [page.Number],
    position: 'diagonal',
    mode: 'underlay',
    font: 'Helvetica-Bold',
    color: [0.85, 0.85, 0.85],
    opacity: 0.4,
  });
}