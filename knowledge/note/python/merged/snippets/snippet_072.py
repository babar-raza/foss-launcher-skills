def test_pdf_writer_converts_image_size_from_centimeters_to_points(self) -> None:
        from aspose.note import Document, Image, Page
        from aspose.note.saving import PdfSaveOptions
        from aspose.note.saving.pdf_writer import write_pdf

        class FakeCanvas:
            instances: list["FakeCanvas"] = []

            def __init__(self, buffer: io.BytesIO) -> None:
                self._buffer = buffer
                self._pagesize = (595, 842)
                self.image_calls: list[tuple[object, float, float, float, float, bool, str]] = []
                FakeCanvas.instances.append(self)

            def setFont(self, name: str, size: int) -> None:  # noqa: N802
                return None

            def drawString(self, x: int, y: int, text: str) -> None:  # noqa: N802
                return None

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

            def drawImage(self, image, x: float, y: float, width: float, height: float, preserveAspectRatio: bool, mask: str) -> None:  # noqa: N802
                self.image_calls.append((image, x, y, width, height, preserveAspectRatio, mask))

            def linkURL(self, url: str, rect: tuple[float, float, float, float], relative: int = 0) -> None:  # noqa: N802
                return None

            def showPage(self) -> None:  # noqa: N802
                return None

            def save(self) -> None:
                self._buffer.write(b"%PDF-fake")

        class FakeImageReader:
            def __init__(self, source) -> None:
                self.source = source

            def getSize(self) -> tuple[int, int]:  # noqa: N802
                return (1024, 768)

        doc = Document()
        page = Page()
        page.AppendChildLast(Image(Bytes=b"image-bytes", Width=10.0, Height=5.0))
        doc.AppendChildLast(page)

        with patch("reportlab.pdfgen.canvas.Canvas", FakeCanvas), patch("reportlab.lib.utils.ImageReader", FakeImageReader):
            write_pdf(doc, PdfSaveOptions())

        canvas = FakeCanvas.instances[0]
        self.assertEqual(len(canvas.image_calls), 1)
        _, x, y, width, height, preserve_aspect_ratio, mask = canvas.image_calls[0]
        self.assertEqual(x, 40)
        self.assertAlmostEqual(y, 842 - 40 - (5.0 * 28.35), places=2)
        self.assertAlmostEqual(width, 10.0 * 28.35, places=2)
        self.assertAlmostEqual(height, 5.0 * 28.35, places=2)
        self.assertTrue(preserve_aspect_ratio)
        self.assertEqual(mask, "auto")