def test_embedded_message_attachment_round_trip_produces_embedded_message_storage(self) -> None:
        parent = MapiMessage.create("Outer", "Parent body")
        child = MapiMessage.create("Inner", "Child body")
        parent.add_embedded_message_attachment(child, filename="inner.msg")

        reader = MsgReader(CFBReader(parent.to_bytes()))
        document = MsgDocument.from_reader(reader)
        attachment_storages = [storage for storage in document.root.storages if storage.role == ATTACHMENT_ROLE]

        self.assertEqual(len(attachment_storages), 1)
        embedded = next((storage for storage in attachment_storages[0].storages if storage.role == EMBEDDED_MESSAGE_ROLE), None)
        self.assertIsNotNone(embedded)
        assert embedded is not None
        self.assertEqual(embedded.name, "__substg1.0_3701000D")
        self.assertEqual(embedded.role, EMBEDDED_MESSAGE_ROLE)
        embedded_entry = reader.cfb_reader.resolve_path(
            ["__attach_version1.0_#00000000", "__substg1.0_3701000D"]
        )
        self.assertIsNotNone(embedded_entry)
        assert embedded_entry is not None
        embedded_header, _ = reader.parse_message_property_stream(embedded_entry.stream_id)
        self.assertEqual(embedded_header.recipient_count, 0)