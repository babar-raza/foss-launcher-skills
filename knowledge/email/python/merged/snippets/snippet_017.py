def test_new_messages_emit_minimal_outlook_compatibility_defaults(self) -> None:
        message = MapiMessage.create("Hello", "Body")
        message.set_property(PropertyId.SENDER_EMAIL_ADDRESS, "sender@example.com")
        message.add_recipient("alice@example.com", display_name="Alice")
        message.add_recipient("bob@example.com", display_name="Bob", recipient_type=2)
        message.add_attachment("a.txt", b"abc", mime_type="text/plain")
        round_tripped = MapiMessage.from_msg_document(MsgDocument.from_reader(MsgReader(CFBReader(message.to_bytes()))))

        self.assertEqual(round_tripped.message_class, "IPM.Note")
        self.assertEqual(
            round_tripped.get_property_value(PropertyId.SENDER_ADDRESS_TYPE),
            "SMTP",
        )
        self.assertEqual(round_tripped.get_property_value(PropertyId.MESSAGE_FLAGS), 17)
        self.assertEqual(round_tripped.get_property_value(PropertyId.DISPLAY_TO), "Alice <alice@example.com>")
        self.assertEqual(round_tripped.get_property_value(PropertyId.DISPLAY_CC), "Bob <bob@example.com>")
        self.assertEqual(round_tripped.get_property_value(PropertyId.INTERNET_CODEPAGE), 20127)
        self.assertIsInstance(round_tripped.get_property_value(0x0071), bytes)
        self.assertEqual(round_tripped.get_property_value(0x3016), True)
        self.assertIsInstance(round_tripped.get_property_value(0x300B), bytes)
        self.assertEqual(round_tripped.recipients[0].properties.get(0x3000).value, 0)
        self.assertIsInstance(round_tripped.recipients[0].properties.get(0x0FF6).value, bytes)
        self.assertEqual(round_tripped.attachments[0].properties.get(0x0FF4).value, 2)
        self.assertEqual(round_tripped.attachments[0].properties.get(0x0FF7).value, 0)