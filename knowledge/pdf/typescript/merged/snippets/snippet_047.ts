function cardGrid(page: Page, labels: string[], opts: CardGridOptions): Box[] {
  const gapX = opts.gapX ?? 14;
  const gapY = opts.gapY ?? 14;
  const labelInset = opts.labelInset ?? 12;
  const labelHeight = opts.labelHeight ?? 22;
  const labelSize = opts.labelSize ?? 11;
  const cardW = (opts.right - opts.left - gapX * (opts.cols - 1)) / opts.cols;
  const cardH = (opts.top - opts.bottom - gapY * (opts.rows - 1)) / opts.rows;

  // Pass 1 — every frame, committed in one apply().
  const frames = page.Graphics();
  const labelBoxes: Box[] = [];
  const inners: Box[] = [];
  labels.forEach((_, i) => {
    const col = i % opts.cols;
    const row = Math.floor(i / opts.cols);
    const x = opts.left + col * (cardW + gapX);
    const y = opts.top - (row + 1) * cardH - row * gapY;
    frames.setFillColor([0.985, 0.985, 0.995])
      .setStrokeColor([0.83, 0.85, 0.92]).setLineWidth(0.5)
      .roundedRect(x, y, cardW, cardH, 6).fillStroke();
    labelBoxes.push([
      x + labelInset, y + cardH - labelHeight - 2, x + cardW - labelInset, y + cardH - 4,
    ]);
    inners.push([
      x + labelInset, y + 10, x + cardW - labelInset, y + cardH - labelHeight - 6,
    ]);
  });
  frames.apply();

  // Pass 2 — labels, on top of committed frames.
  labels.forEach((label, i) => {
    addText(page, label, labelBoxes[i], {
      font: 'Helvetica-Bold', size: labelSize, color: NAVY,
    });
  });

  return inners;
}