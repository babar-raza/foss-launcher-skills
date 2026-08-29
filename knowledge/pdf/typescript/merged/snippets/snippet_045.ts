function addText(page: Page, text: string, box: Box, style: TextStyle = {}): void {
  const size = style.size ?? 12;
  page.AddTextBlock(text, xywh(box), {
    font: style.font ?? 'Helvetica',
    fontSize: size,
    color: style.color,
    opacity: style.opacity,
    align: style.align,
    valign: style.valign,
    leading: (style.lineSpacing ?? 1) * size,
    underline: style.underline,
    strikethrough: style.strikethrough,
    background: style.background,
    rotate: style.rotate,
    behind: style.behind,
  });
}