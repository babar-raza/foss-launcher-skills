def test_high_level_message_round_trip_preserves_core_msg_structure(self) -> None:
        message = MapiMessage.create("Hello", "Body")
        message.add_recipient("alice@example.com", display_name="Alice")
        message.add_attachment("a.txt", b"abc", mime_type="text/plain")
        message.set_named_property(
            MapiNamedProperty.string("Keywords", PS_PUBLIC_STRINGS),
            PropertyTypeCode.PTYP_MULTIPLE_STRING8,
            ["one", "two"],
        )

        reader = MsgReader(CFBReader(message.to_bytes()))
        document = MsgDocument.from_reader(reader)
        round_tripped = MapiMessage.from_msg_document(document)

        self.assertEqual(reader.top_level_header.recipient_count, 1)
        self.assertEqual(reader.top_level_header.attachment_count, 1)
        self.assertEqual(len(tuple(reader.iter_recipient_storages())), 1)
        self.assertEqual(len(tuple(reader.iter_attachment_storages())), 1)

        nameid_storage = reader.storage_layout.named_property_mapping_storage
        nameid_stream_names = {
            child.name for child in reader.cfb_reader.iter_children(nameid_storage.stream_id) if child.is_stream()
        }
        self.assertIn("__substg1.0_00020102", nameid_stream_names)
        self.assertIn("__substg1.0_00030102", nameid_stream_names)
        self.assertIn("__substg1.0_00040102", nameid_stream_names)

        recipient_entry = next(reader.iter_recipient_storages())
        attachment_entry = next(reader.iter_attachment_storages())
        _, recipient_props = reader.parse_subobject_property_stream(recipient_entry.stream_id)
        _, attachment_props = reader.parse_subobject_property_stream(attachment_entry.stream_id)
        self.assertGreater(len(recipient_props), 0)
        self.assertGreater(len(attachment_props), 0)

        named = round_tripped.get_named_property(
            MapiNamedProperty.string("Keywords", PS_PUBLIC_STRINGS),
            int(PropertyTypeCode.PTYP_MULTIPLE_STRING8),
        )
        self.assertEqual(round_tripped.subject, "Hello")
        self.assertEqual(round_tripped.body, "Body")
        self.assertEqual(len(round_tripped.recipients), 1)
        self.assertEqual(len(round_tripped.attachments), 1)
        self.assertIsNotNone(named)
        assert named is not None
        self.assertEqual(named.value, ["one", "two"])