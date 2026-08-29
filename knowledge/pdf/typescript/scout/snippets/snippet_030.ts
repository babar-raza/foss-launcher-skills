function imposedSheetThumb(doc: Document, label: string): Thumb {
  return renderPageThumb(doc.Pages[0], label);
}