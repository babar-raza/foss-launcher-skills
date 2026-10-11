import aspose.words_foss as aw

doc = aw.Document("report.docx")
text = doc.get_text()
print(text)
