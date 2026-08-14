def test_pdf_writer_renders_note_tags(self) -> None:
        from aspose.note import Document, NoteTag, Page, RichText
        from aspose.note.saving import PdfSaveOptions
        from aspose.note.saving.pdf_writer import write_pdf

        class FakeCanvas:
            instances: list["FakeCanvas"] = []

            def __init__(self, buffer: io.BytesIO) -> None:
                self._buffer = buffer
                self._pagesize = (595, 842)
                self.drawn_strings: list[str] = []
                self.font_calls: list[tuple[str, float]] = []
                self.fill_colors: list[tuple[float, float, float]] = []
                self.stroke_colors: list[tuple[float, float, float]] = []
                self.rect_calls: list[tuple[float, float, float, float, int, int]] = []
                self.line_calls: list[tuple[float, float, float, float]] = []
                FakeCanvas.instances.append(self)

            def setFont(self, name: str, size: int) -> None:  # noqa: N802
                self.font_calls.append((name, size))

            def drawString(self, x: int, y: int, text: str) -> None:  # noqa: N802
                self.drawn_strings.append(text)

            def setFillColorRGB(self, r: float, g: float, b: float) -> None:  # noqa: N802
                self.fill_colors.append((r, g, b))

            def setStrokeColorRGB(self, r: float, g: float, b: float) -> None:  # noqa: N802
                self.stroke_colors.append((r, g, b))

            def rect(self, x: float, y: float, width: float, height: float, stroke: int = 0, fill: int = 0) -> None:
                self.rect_calls.append((x, y, width, height, stroke, fill))

            def line(self, x1: float, y1: float, x2: float, y2: float) -> None:
                self.line_calls.append((x1, y1, x2, y2))

            def stringWidth(self, text: str, font_name: str, font_size: float) -> float:  # noqa: N802
                return len(text) * font_size * 0.55

            def drawImage(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003, N802
                return None

            def showPage(self) -> None:  # noqa: N802
                return None

            def save(self) -> None:
                self._buffer.write(b"%PDF-fake")

        tagged = RichText(Text="Tagged body")
        tagged.Tags.extend(
            [
            NoteTag.CreateYellowStar("Важно"),
            NoteTag.CreateQuestionMark("Вопрос"),
            NoteTag.CreateMusicalNote("Послушать музыку"),
            ]
        )

        doc = Document()
        page = Page()
        page.AppendChildLast(tagged)
        doc.AppendChildLast(page)

        with patch("reportlab.pdfgen.canvas.Canvas", FakeCanvas):
            write_pdf(doc, PdfSaveOptions())

        canvas = FakeCanvas.instances[0]
        self.assertIn("Tagged body", canvas.drawn_strings)
        self.assertTrue(canvas.rect_calls)
        self.assertTrue(canvas.line_calls)