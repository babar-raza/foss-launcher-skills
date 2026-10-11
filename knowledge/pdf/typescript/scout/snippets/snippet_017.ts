function addBookmarks(doc: Document, sections: Section[]): void {
  const items: OutlineItem[] = sections.map((s) => {
    const item: OutlineItem = { Title: s.title, Dest: { name: s.dest } };
    const color = OUTLINE_COLORS[s.subtype];
    if (color) item.Color = color;
    if (BOLD_SUBTYPES.has(s.subtype)) item.Bold = true;
    if (s.subtype === 'sales') {
      item.Open = true;
      item.Children = ['Pasta', 'Pizza', 'Antipasti', 'Desserts', 'Beverages']
        .map((cat) => ({ Title: cat, Dest: { name: s.dest } }));
    }
    return item;
  });
  doc.SetOutlines(items);
}