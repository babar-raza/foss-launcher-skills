def test_pdf_writer_renders_tags_in_visual_reverse_order(self) -> None:
        from aspose.note import Document, NoteTag, Page, RichText
        from aspose.note.saving import PdfSaveOptions
        from aspose.note.saving import pdf_writer

        class FakeCanvas:
            def __init__(self, buffer: io.BytesIO) -> None:
                self._buffer = buffer
                self._pagesize = (595, 842)

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

        rendered_shapes: list[int | None] = []

        def _capture_tag(pdf, tag, x: float, baseline_y: float, options):
            rendered_shapes.append(getattr(tag, "Icon", None))
            return 10.0

        with patch("reportlab.pdfgen.canvas.Canvas", FakeCanvas), patch.object(pdf_writer, "_render_note_tag", side_effect=_capture_tag):
            pdf_writer.write_pdf(doc, PdfSaveOptions())

        self.assertEqual(rendered_shapes, [121, 15, 13])