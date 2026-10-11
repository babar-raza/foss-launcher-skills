def test_embeds_defined_type42_font_program(self) -> None:
        resources = Path(__file__).resolve().parents[2] / "resources"
        regular_src = resources / "LiberationSerif-Regular.ttf"
        if not regular_src.exists():
            self.skipTest("font resources not available")
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            font_path = tmp / "DefinedType42.ttf"
            shutil.copyfile(regular_src, font_path)

            cache = FontCache()
            cache.load(tmpdir)
            resolver = FontResolver(additional_fonts_folder=tmpdir, font_cache=cache)
            metrics = cache.metrics_for(font_path)
            data = font_path.read_bytes()
            resolver.register_defined_font(
                "f-0-0",
                FontResource(
                    name="f-0-0",
                    font_type="Type42",
                    units_per_em=metrics.units_per_em,
                    encoding={},
                    glyph_widths={},
                    substitute=False,
                    code_widths=metrics.code_widths,
                    font_program=data,
                ),
            )

            builder = RenderModelBuilder()
            builder.begin_page(200, 200)
            builder.add_text("AXISPOINT", "f-0-0", 12, Matrix.identity(), None)
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
            self.assertIn(b"+f-0-0", pdf)