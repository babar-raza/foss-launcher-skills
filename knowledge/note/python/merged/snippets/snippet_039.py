def test_parser_materializes_incremental_current_roots(self) -> None:
        from aspose.note._internal.onestore.parser import parse_onestore_file

        for fixture_name in ("SimpleTable.one", "TagSizes.one", "3ImagesWithDifferentAlignment.one"):
            fixture_path = _fixture_path(fixture_name)
            if fixture_path is None:
                raise unittest.SkipTest(f"{fixture_name} not found")

            parsed = parse_onestore_file(fixture_path)
            content_space = max(parsed.object_spaces, key=lambda item: len(item.revisions))

            default_root = content_space.get_latest_root(1)
            self.assertIsNotNone(default_root, fixture_name)
            if default_root is None:
                raise AssertionError(f"expected default root for {fixture_name}")
            self.assertIn(default_root, content_space.objects, fixture_name)
            self.assertEqual(content_space.objects[default_root].jcid_name, "PageManifestNode", fixture_name)