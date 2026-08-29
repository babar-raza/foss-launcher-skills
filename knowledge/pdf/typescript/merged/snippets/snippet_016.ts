function addTOC(page: Page, sections: Section[]): void {
  const w = pageWidth(page);
  const h = pageHeight(page);

  sectionHeader(page, 'Contents',
    'page.AddTOC  •  dotted leaders  •  logical page labels  •  clickable links');

  // No explicit `label`: AddTOC defaults to each target page's /PageLabels
  // label, which main.ts set before calling this. A sequential "N." index is
  // folded into the title so the sales report's continuation page creates no
  // gap in the numbering.
  page.AddTOC(
    sections.map((s, i) => ({ title: `${i + 1}.  ${s.title}`, page: s.page.Number })),
    [72, 160, w - 172, h - 340],
    {
      font: 'Helvetica',
      fontSize: 13,
      color: [0.1, 0.1, 0.15],
      rowGap: 18,
    },
  );

  addText(page, 'Click any title above to jump to the section.',
    [50, 120, w - 50, 140],
    { font: 'Helvetica-Oblique', size: 10, color: [0.55, 0.55, 0.6], align: 'center' });
}