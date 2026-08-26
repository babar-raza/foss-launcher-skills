import aspose.words_foss as aw

doc = aw.Document("report.docx")
md_opts = aw.saving.MarkdownSaveOptions()
md_opts.encoding = "utf-8-sig"
doc.save("report.md", md_opts)
