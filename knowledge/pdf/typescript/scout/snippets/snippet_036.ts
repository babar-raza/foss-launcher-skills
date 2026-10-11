function runAutoTag(doc: Document): AutoTagReport {
  return doc.AutoTag({ lang: 'en-US', title: DOC_TITLE, alt: altForImage, tables: true });
}