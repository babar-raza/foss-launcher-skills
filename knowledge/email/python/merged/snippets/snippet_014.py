def test_readme_quick_start_round_trip(self) -> None:
        message = MapiMessage.create("Hello", "Body")
        message.set_property(PropertyId.SENDER_NAME, "Build Agent")
        message.set_property(PropertyId.SENDER_EMAIL_ADDRESS, "build.agent@example.com")
        message.set_property(
            PropertyId.MESSAGE_DELIVERY_TIME,
            datetime.datetime(2026, 3, 15, 10, 30, tzinfo=datetime.timezone.utc),
        )
        message.add_recipient("alice@example.com", display_name="Alice Example")
        message.add_attachment("hello.txt", b"sample attachment\n", mime_type="text/plain")

        loaded = MapiMessage.from_msg_document(MsgDocument.from_reader(MsgReader(CFBReader(message.to_bytes()))))
        email_message = loaded.to_email_message()

        self.assertEqual(email_message["Subject"], "Hello")
        self.assertEqual(email_message["From"], "Build Agent <build.agent@example.com>")
        self.assertEqual(email_message["To"], "Alice Example <alice@example.com>")