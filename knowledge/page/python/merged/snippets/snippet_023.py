def test_embeds_type42_without_cmap_by_synthesized_cmap(self) -> None:
        sample = Path(__file__).resolve().parents[2] / "testdata/ps/functional/FONTS10/TrueType.ps"
        if not sample.exists():
            self.skipTest("sample Type42 PS not available")

        resolver = FontResolver(additional_fonts_folder="testdata/ps/necessary_fonts")
        builder = RenderModelBuilder()
        registry = OperatorRegistry()
        image_store = PsImageStore()
        register_base_operators(registry)
        register_core_graphics_operators(registry, builder)
        register_color_operators(registry, builder)
        register_image_operators(registry, builder, image_store)
        register_text_operators(registry, builder, resolver)
        interpreter = PsInterpreter(registry)
        pipeline = PsConversionPipeline(
            interpreter,
            registry,
            builder,
            font_resolver=resolver,
            image_store=image_store,
        )
        doc = pipeline.build_render_model(sample.read_bytes())
        used_codes: dict[str, set[int]] = {}
        for page in doc.pages:
            for command in page.commands:
                if hasattr(command, "font_ref") and hasattr(command, "text"):
                    used_codes.setdefault(command.font_ref, set()).update(ord(ch) for ch in command.text)
        self.assertIn("f-0-0", used_codes)

        embedded = build_embedded_font("f-0-0", used_codes["f-0-0"], resolver)
        self.assertIsNotNone(embedded)
        assert embedded is not None
        self.assertGreater(len(embedded.font_file), 0)
        self.assertIn(ord("A"), embedded.char_code_map)
        self.assertTrue(has_ttf_table(embedded.font_file, b"cmap"))