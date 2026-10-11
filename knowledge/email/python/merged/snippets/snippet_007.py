def test_manual_top_level_property_stream_parsing(self) -> None:
        property_tag = (int(CommonMessagePropertyId.STORE_SUPPORT_MASK) << 16) | int(PropertyTypeCode.PTYP_INTEGER32)
        entry = struct.pack("<II", property_tag, 0x00000006) + struct.pack("<I", 0x00040000).ljust(8, b"\x00")
        payload = (
            b"\xAA" * 8
            + struct.pack("<I", 5)
            + struct.pack("<I", 7)
            + struct.pack("<I", 1)
            + struct.pack("<I", 2)
            + b"\xBB" * 8
            + entry
        )

        header, entries = MsgReader.parse_top_level_property_stream(payload)

        self.assertEqual(header.reserved_0, b"\xAA" * 8)
        self.assertEqual(header.next_recipient_id, 5)
        self.assertEqual(header.next_attachment_id, 7)
        self.assertEqual(header.recipient_count, 1)
        self.assertEqual(header.attachment_count, 2)
        self.assertEqual(header.reserved_1, b"\xBB" * 8)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].property_tag, property_tag)
        self.assertEqual(entries[0].flags, 0x00000006)
        self.assertEqual(struct.unpack_from("<I", entries[0].value, 0)[0], 0x00040000)