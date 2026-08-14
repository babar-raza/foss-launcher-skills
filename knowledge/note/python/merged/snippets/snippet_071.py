def test_pdf_writer_preserves_spaces_and_inline_metadata(self) -> None:
        from aspose.note import Document, Page, RichText, Title
        from aspose.note.saving import PdfSaveOptions
        from aspose.note.saving.pdf_writer import write_pdf

        class FakeCanvas:
            instances: list["FakeCanvas"] = []

            def __init__(self, buffer: io.BytesIO) -> None:
                self._buffer = buffer
                self._pagesize = (595, 842)
                self.drawn_strings: list[tuple[int, int, str]] = []
                FakeCanvas.instances.append(self)

            def setFont(self, name: str, size: int) -> None:  # noqa: N802
                return None

            def drawString(self, x: int, y: int, text: str) -> None:  # noqa: N802
                self.drawn_strings.append((x, y, text))

            def setFillColorRGB(self, r: float, g: float, b: float) -> None:  # noqa: N802
                return None

            def setStrokeColorRGB(self, r: float, g: float, b: float) -> None:  # noqa: N802
                return None

            def rect(self, x: float, y: float, width: float, height: float, stroke: int = 0, fill: int = 0) -> None:
                return None

            def line(self, x1: float, y1: float, x2: float, y2: float) -> None:
                return None

            def stringWidth(self, text: str, font_name: str, font_size: float) -> float:  # noqa: N802
                return len(text) * font_size * 0.55

            def drawImage(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003, N802
                return None

            def linkURL(self, url: str, rect: tuple[float, float, float, float], relative: int = 0) -> None:  # noqa: N802
                return None

            def showPage(self) -> None:  # noqa: N802
                return None

            def save(self) -> None:
                self._buffer.write(b"%PDF-fake")

        doc = Document()
        page = Page()
        title = Title()
        title.TitleText = RichText(Text="One hyperlink")
        title.TitleDate = RichText(Text="2025-01-01")
        title.TitleTime = RichText(Text="13:12")
        page.Title = title
        page.AppendChildLast(title)
        page.AppendChildLast(RichText(Text="This is hyperlink."))
        doc.AppendChildLast(page)

        with patch("reportlab.pdfgen.canvas.Canvas", FakeCanvas):
            write_pdf(doc, PdfSaveOptions())

        canvas = FakeCanvas.instances[0]
        texts = [text for _, _, text in canvas.drawn_strings]
        self.assertIn("One hyperlink", texts)
        self.assertIn("This is hyperlink.", texts)

        date_call = next(item for item in canvas.drawn_strings if item[2] == "2025-01-01")
        time_call = next(item for item in canvas.drawn_strings if item[2] == "13:12")
        self.assertEqual(date_call[1], time_call[1])
        self.assertGreater(time_call[0], date_call[0])