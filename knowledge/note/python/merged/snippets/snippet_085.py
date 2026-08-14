from aspose.note import Document

doc = Document("testfiles/SimpleTable.one")
print(doc.DisplayName)
pages = list(doc)
print(len(pages))

# pages are direct children of Document
for page in pages:
    print(page.Title.TitleText.Text)
