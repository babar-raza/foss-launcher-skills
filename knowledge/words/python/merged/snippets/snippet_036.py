import aspose.words_foss as aw

doc = aw.Document("report.docx")
ooxml_opts = aw.saving.OoxmlSaveOptions()
ooxml_opts.compression_level = aw.saving.CompressionLevel.MAXIMUM
doc.save("report-max-compression.docx", ooxml_opts)
