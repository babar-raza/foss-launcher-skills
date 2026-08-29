function addTaggedShowcase(doc: Document, page: Page, report: AutoTagReport): void {
  sectionHeader(page, 'Tagged PDF & Logical Structure',
    'AutoTag over the whole document  •  /Figure vs /Artifact  •  hand-authored elements');

  const root = doc.GetStructTree();
  const total = report.headings + report.paragraphs + report.figures
    + report.artifacts + report.tables;

  addText(page,
    'One AutoTag pass ran over every page of this document once its content was '
    + 'final. It derives headings from font-size ranks, paragraphs from text '
    + 'blocks, tables from ruling geometry, and decides per image whether to '
    + 'emit a /Figure with /Alt or an /Artifact. The counts below are what it '
    + 'actually produced on this run.',
    [50, 636, 545, 700], { size: 10, color: INK, lineSpacing: 1.35 });

  const inners = cardGrid(page, [
    'AutoTag — what it produced',
    'Structure tree — first elements',
    'Images — /Figure vs /Artifact',
    'Hand-authored elements',
  ], { cols: 2, rows: 2, left: 50, right: 545, top: 620, bottom: 150 });

  // Card 1 — the report counts.
  const counts: Array<[string, number]> = [
    ['Headings (/H1../H6)', report.headings],
    ['Paragraphs (/P)', report.paragraphs],
    ['Tables (/Table)', report.tables],
    ['Figures (/Figure)', report.figures],
    ['Artifacts', report.artifacts],
    ['Total elements', total],
  ];
  counts.forEach(([label, n], i) => {
    const y = inners[0][3] - 16 - i * 15;
    addText(page, label, [inners[0][0], y, inners[0][2] - 46, y + 12],
      { size: 9.5, color: INK });
    addText(page, String(n), [inners[0][2] - 44, y, inners[0][2], y + 12],
      { size: 9.5, color: NAVY, align: 'right', font: 'Helvetica-Bold' });
  });

  // Card 2 — an excerpt of the real tree.
  const lines = root ? outlineTree(root.Children, 12) : ['(no structure tree)'];
  lines.forEach((line, i) => {
    const y = inners[1][3] - 14 - i * 11;
    addText(page, line, [inners[1][0], y, inners[1][2], y + 10],
      { size: 7.5, color: MUTED });
  });

  // Card 3 — the alt-text rule.
  addText(page,
    'ImageEvent carries geometry, not identity — no page, no XObject name — so '
    + 'the alt callback decides from the quad. Anything under 40pt on its long '
    + 'edge is decoration at this scale and becomes an /Artifact; larger images '
    + `become a /Figure carrying /Alt. This run: ${report.figures} figure(s), `
    + `${report.artifacts} artifact(s).`,
    [inners[2][0], inners[2][1], inners[2][2], inners[2][3] - 4],
    { size: 8.5, color: INK, lineSpacing: 1.3 });

  // Card 4 — why hand-tagging exists here at all.
  addText(page,
    'This page, and the three that follow it, are filled after the AutoTag pass '
    + '— they report on the finished document, so they cannot exist before it. '
    + 'They are tagged by hand instead, through StructTreeRoot.Append plus '
    + 'StructElement.MarkContent. That is the authoring API beside the heuristic '
    + 'one, and it cannot double-tag: AutoTag has already run and does not run '
    + 'again.',
    [inners[3][0], inners[3][1], inners[3][2], inners[3][3] - 4],
    { size: 8.5, color: INK, lineSpacing: 1.3 });

  addText(page,
    'AutoTag({ title }) also sets /ViewerPreferences /DisplayDocTitle — a title '
    + 'alone does not satisfy PDF/UA unless the viewer is told to show it. The '
    + 'validation section that follows reports the result.',
    [50, 112, 545, 140], { size: 8.5, color: MUTED, lineSpacing: 1.35 });
}