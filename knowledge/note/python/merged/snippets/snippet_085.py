from aspose.note import Document

doc = Document("SimpleTable.one")
print(doc.DisplayName)
for page in doc:
    print(page.Title.TitleText.Text)
