def test_branded_namespace_exports_publishable_modules(self) -> None:
        self.assertIs(branded_msg.MapiMessage, MapiMessage)
        self.assertIs(branded_msg.MsgReader, MsgReader)
        self.assertIs(branded_msg.MsgWriter, MsgWriter)
        self.assertIs(branded_msg.PropertyId, PropertyId)
        self.assertIs(branded_cfb.CFBReader, CFBReader)
        self.assertIs(branded_cfb.CFBWriter, CFBWriter)