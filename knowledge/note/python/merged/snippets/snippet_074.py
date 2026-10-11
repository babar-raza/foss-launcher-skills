def test_pdf_writer_creates_clickable_hyperlinks(self) -> None:
        from aspose.note import Document
        from aspose.note.saving import PdfSaveOptions
        from aspose.note.saving.pdf_writer import write_pdf

        class FakeCanvas:
            instances: list["FakeCanvas"] = []

            def __init__(self, buffer: io.BytesIO) -> None:
                self._buffer = buffer
                self._pagesize = (595, 842)
                self.drawn_strings: list[str] = []
                self.link_calls: list[tuple[str, tuple[float, float, float, float], int]] = []
                FakeCanvas.instances.append(self)

            def setFont(self, name: str, size: int) -> None:  # noqa: N802
                return None

            def drawString(self, x: int, y: int, text: str) -> None:  # noqa: N802
                self.drawn_strings.append(text)

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
                self.link_calls.append((url, rect, relative))

            def showPage(self) -> None:  # noqa: N802
                return None

            def save(self) -> None:
                self._buffer.write(b"%PDF-fake")

        doc = Document(self.path)
        with patch("reportlab.pdfgen.canvas.Canvas", FakeCanvas):
            write_pdf(doc, PdfSaveOptions())

        canvas = FakeCanvas.instances[0]
        self.assertTrue(canvas.link_calls)
        self.assertTrue(any(url == "https://www.google.com" for url, _, _ in canvas.link_calls))