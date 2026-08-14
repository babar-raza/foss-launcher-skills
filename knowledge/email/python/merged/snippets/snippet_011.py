def test_reader_rejects_invalid_recipient_storage_name(self) -> None:
        root = CFBStorage(ROOT_ENTRY_NAME)
        root.add_storage(CFBStorage(NAMED_PROPERTY_MAPPING_STORAGE_NAME))
        root.add_stream(CFBStream(PROPERTY_STREAM_NAME, _top_level_property_stream(recipient_count=1)))
        invalid_recipient = root.add_storage(CFBStorage("__recip_version1.0_bad"))
        invalid_recipient.add_stream(CFBStream(PROPERTY_STREAM_NAME, _subobject_property_stream()))

        with self.assertRaises(MsgError):
            MsgReader(CFBReader(CFBWriter.to_bytes(CFBDocument(root=root))))