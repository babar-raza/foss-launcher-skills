import aspose.words_foss as aw

for path in ("report.docx", "legacy.doc", "notes.rtf"):
    doc = aw.Document(path)
    doc.save(f"{path}.pdf", aw.SaveFormat.PDF)
