function handTagPage(doc: Document, page: Page, heading: string): void {
  const root = doc.GetStructTree();
  if (!root) throw new Error('handTagPage: the document is not tagged yet');
  for (const block of page.GetStructuredText()) {
    const text = block.text.trim();
    if (text.length === 0) continue;
    const el = root.Append(text.startsWith(heading) ? 'H2' : 'P');
    el.MarkContent(page, block.quad);
  }
}