def test_attachment_with_tag_fixture_has_tags_somewhere(self) -> None:
        p = _fixture_path("AttachedFileWithTag.one")
        if p is None:
            raise unittest.SkipTest("AttachedFileWithTag.one not found")

        from aspose.note import AttachedFile, Document

        doc = Document(p)
        atts = doc.GetChildNodes(AttachedFile)
        self.assertGreaterEqual(len(atts), 1)

        # Strict: this fixture is expected to include note tags.
        tags = _collect_all_tags(doc)
        self.assertGreaterEqual(len(tags), 1)
        self.assertTrue(any(_tag_is_meaningful(t) for t in tags))