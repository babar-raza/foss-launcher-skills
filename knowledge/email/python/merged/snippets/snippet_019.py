from datetime import datetime, timezone

from aspose.email_foss import msg

message = msg.MapiMessage.create("Hello", "Body")
message.set_property(msg.PropertyId.SENDER_NAME, "Build Agent")
message.set_property(msg.PropertyId.SENDER_EMAIL_ADDRESS, "build.agent@example.com")
message.set_property(msg.PropertyId.MESSAGE_DELIVERY_TIME, datetime(2026, 3, 15, 10, 30, tzinfo=timezone.utc))
message.add_recipient("alice@example.com", display_name="Alice Example")
message.add_attachment("hello.txt", b"sample attachment\n", mime_type="text/plain")
message.save("example-message.msg")

with msg.MapiMessage.from_file("example-message.msg") as loaded:
    email_message = loaded.to_email_message()
    print(email_message["Subject"])
