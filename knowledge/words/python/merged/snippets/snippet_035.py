import aspose.words_foss as aw

doc = aw.Document("report.docx")
ooxml_opts = aw.saving.OoxmlSaveOptions()
ooxml_opts.pretty_format = True
doc.save("report-pretty.docx", ooxml_opts)
