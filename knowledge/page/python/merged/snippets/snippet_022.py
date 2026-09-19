def test_embedded_font_objects_present(self) -> None:
        resources = Path(__file__).resolve().parents[2] / "resources"
        regular_src = resources / "LiberationSerif-Regular.ttf"
        if not regular_src.exists():
            self.skipTest("font resources not available")
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            font_path = tmp / "UnitTestFont-Regular.ttf"
            shutil.copyfile(regular_src, font_path)

            cache = FontCache()
            cache.load(tmpdir)
            resolver = FontResolver(additional_fonts_folder=tmpdir, font_cache=cache)

            builder = RenderModelBuilder()
            builder.begin_page(200, 200)
            builder.add_text("Hello", "UnitTestFont", 12, Matrix.identity(), None)
            builder.end_page()
            doc = builder.document()

            metadata = PdfMetadata(
                title="",
                creator="",
                producer="Aspose.Page FOSS for Python",
                creation_date="D:20260101000000",
                mod_date="D:20260101000000",
                trapped=False,
            )

            def font_provider(font_name: str, used_codes: set[int]):
                return build_embedded_font(font_name, used_codes, resolver)

            writer = PdfWriter(metadata, no_compression=True, font_provider=font_provider)
            pdf = writer.write(doc)

            self.assertIn(b"/FontFile2", pdf)
            self.assertIn(b"/ToUnicode", pdf)
            self.assertIn(b"+UnitTestFont", pdf)