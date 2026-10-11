function renderPageThumb(page: Page, label: string): Thumb {
  const img = page.ToImage({ scale: 96 / 72 });
  const w = page.Rect[2] - page.Rect[0];
  const h = page.Rect[3] - page.Rect[1];
  return { img, aspect: w / h, label };
}