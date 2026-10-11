def test_high_level_property_api_accepts_common_message_property_id(self) -> None:
        message = MapiMessage.create()
        message.set_property(CommonMessagePropertyId.SUBJECT, PropertyTypeCode.PTYP_STRING, "Enum subject")

        property_object = message.get_property(CommonMessagePropertyId.SUBJECT, int(PropertyTypeCode.PTYP_STRING))
        property_value = message.get_property_value(CommonMessagePropertyId.SUBJECT)

        self.assertIsNotNone(property_object)
        assert property_object is not None
        self.assertEqual(property_object.property_id, int(CommonMessagePropertyId.SUBJECT))
        self.assertEqual(property_object.value, "Enum subject")
        self.assertEqual(property_value, "Enum subject")