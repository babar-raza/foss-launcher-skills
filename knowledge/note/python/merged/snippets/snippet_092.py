from aspose.note import Document, DocumentVisitor, Page, Image, RichText


class Counter(DocumentVisitor):
  def __init__(self) -> None:
    self.pages = 0
    self.rich_texts = 0
    self.images = 0

  def VisitPageStart(self, page: Page) -> None:  # noqa: N802
    self.pages += 1

  def VisitRichTextStart(self, rich_text: RichText) -> None:  # noqa: N802
    self.rich_texts += 1

  def VisitImageStart(self, image: Image) -> None:  # noqa: N802
    self.images += 1


doc = Document("testfiles/3ImagesWithDifferentAlignment.one")
counter = Counter()
doc.Accept(counter)
print(counter.pages, counter.rich_texts, counter.images)
