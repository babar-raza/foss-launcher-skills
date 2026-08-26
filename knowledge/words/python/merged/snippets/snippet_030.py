import aspose.words_foss as aw

doc = aw.Document("report.docx")

md_opts = aw.saving.MarkdownSaveOptions()
md_opts.export_underline_formatting = True
doc.save("report.md", md_opts)

pdf_opts = aw.saving.PdfSaveOptions()
doc.save("report.pdf", pdf_opts)
