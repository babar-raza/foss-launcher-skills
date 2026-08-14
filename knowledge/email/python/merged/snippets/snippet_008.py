def test_property_stream_parsers_reject_misaligned_payloads(self) -> None:
        with self.assertRaises(MsgError):
            MsgReader.parse_top_level_property_stream(b"\x00" * 33)
        with self.assertRaises(MsgError):
            MsgReader.parse_subobject_property_stream_data(b"\x00" * 9)
        with self.assertRaises(MsgError):
            MsgReader.parse_subobject_property_stream_data(b"\x00" * 25)