def test_large_v3_document_emits_difat(self) -> None:
        payload = b"Z" * (512 * 15000)

        root = CFBStorage(ROOT_ENTRY_NAME)
        root.add_stream(CFBStream("Huge", payload))

        reader = CFBReader(CFBWriter.to_bytes(CFBDocument(root=root, major_version=3)))

        self.assertGreater(reader.header.number_of_fat_sectors, 109)
        self.assertGreater(reader.header.number_of_difat_sectors, 0)
        stream_entry = reader.resolve_path(["Huge"])
        self.assertIsNotNone(stream_entry)
        assert stream_entry is not None
        self.assertEqual(reader.get_stream_data(stream_entry.stream_id), payload)