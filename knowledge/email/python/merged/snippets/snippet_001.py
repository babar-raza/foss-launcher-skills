def test_v3_round_trip_routes_small_streams_through_mini_stream(self) -> None:
        small_payload = b"mini-stream-payload"
        large_payload = (b"0123456789ABCDEF" * 400)

        root = CFBStorage(ROOT_ENTRY_NAME)
        root.add_stream(CFBStream("Small", small_payload))
        nested = root.add_storage(CFBStorage("Nested"))
        nested.add_stream(CFBStream("Large", large_payload))

        reader = CFBReader(CFBWriter.to_bytes(CFBDocument(root=root, major_version=3)))

        self.assertEqual(reader.major_version, 3)
        self.assertEqual(reader.sector_size, 512)
        self.assertEqual(reader.header.number_of_directory_sectors, 0)
        self.assertGreater(len(reader.mini_fat), 0)

        small_entry = reader.resolve_path(["Small"])
        large_entry = reader.resolve_path(["Nested", "Large"])
        self.assertIsNotNone(small_entry)
        self.assertIsNotNone(large_entry)
        assert small_entry is not None
        assert large_entry is not None

        self.assertLess(small_entry.stream_size, reader.header.mini_stream_cutoff_size)
        self.assertGreaterEqual(large_entry.stream_size, reader.header.mini_stream_cutoff_size)
        self.assertEqual(reader.get_stream_data(small_entry.stream_id), small_payload)
        self.assertEqual(reader.get_stream_data(large_entry.stream_id), large_payload)
        self.assertGreater(reader.root_entry.stream_size, 0)