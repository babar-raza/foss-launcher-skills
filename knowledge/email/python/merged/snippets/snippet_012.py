def test_strict_writer_rejects_named_property_mapping_in_embedded_message(self) -> None:
        root = MsgStorage(name=ROOT_ENTRY_NAME, role=MESSAGE_ROLE)
        root.add_storage(MsgStorage(name=NAMED_PROPERTY_MAPPING_STORAGE_NAME))
        root.add_stream(MsgStream(PROPERTY_STREAM_NAME, _top_level_property_stream(attachment_count=1)))

        attachment = root.add_storage(MsgStorage(name="__attach_version1.0_#00000000", role=ATTACHMENT_ROLE))
        attachment.add_stream(MsgStream(PROPERTY_STREAM_NAME, _attachment_property_stream()))

        embedded = attachment.add_storage(MsgStorage(name="__substg1.0_3701000D", role=EMBEDDED_MESSAGE_ROLE))
        embedded.add_stream(MsgStream(PROPERTY_STREAM_NAME, _top_level_property_stream()))
        embedded.add_storage(MsgStorage(name=NAMED_PROPERTY_MAPPING_STORAGE_NAME))

        with self.assertRaises(MsgError):
            MsgWriter.to_bytes(MsgDocument(root=root, strict=True))