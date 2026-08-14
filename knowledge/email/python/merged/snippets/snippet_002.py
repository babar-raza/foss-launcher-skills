def test_v4_round_trip_uses_4096_byte_sectors(self) -> None:
        payload = b"A" * 7000

        root = CFBStorage(ROOT_ENTRY_NAME)
        root.add_stream(CFBStream("Payload", payload))

        reader = CFBReader(CFBWriter.to_bytes(CFBDocument(root=root, major_version=4)))

        self.assertEqual(reader.major_version, 4)
        self.assertEqual(reader.sector_size, 4096)
        self.assertEqual(reader.mini_sector_size, 64)
        self.assertGreater(reader.header.number_of_directory_sectors, 0)

        stream_entry = reader.resolve_path(["Payload"])
        self.assertIsNotNone(stream_entry)
        assert stream_entry is not None
        self.assertEqual(reader.get_stream_data(stream_entry.stream_id), payload)