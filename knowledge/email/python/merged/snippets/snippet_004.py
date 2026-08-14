def test_writer_rejects_duplicate_sibling_names_under_cfb_comparison_rules(self) -> None:
        root = CFBStorage(ROOT_ENTRY_NAME)
        root.add_stream(CFBStream("ab", b"left"))
        root.add_stream(CFBStream("AB", b"right"))

        with self.assertRaises(CFBError):
            CFBWriter.to_bytes(CFBDocument(root=root))