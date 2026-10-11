def test_high_level_property_api_accepts_typed_property_id_short_form(self) -> None:
        message = MapiMessage.create()
        delivery_time = datetime.datetime(2026, 3, 15, 10, 30, tzinfo=datetime.timezone.utc)
        message.set_property(PropertyId.SUBJECT, "Typed subject")
        message.set_property(PropertyId.MESSAGE_DELIVERY_TIME, delivery_time)

        subject_property = message.get_property(PropertyId.SUBJECT)
        subject_value = message.get_property_value(PropertyId.SUBJECT)
        time_property = message.get_property(PropertyId.MESSAGE_DELIVERY_TIME)
        time_value = message.get_property_value(PropertyId.MESSAGE_DELIVERY_TIME)

        self.assertIsNotNone(subject_property)
        self.assertIsNotNone(time_property)
        assert subject_property is not None
        assert time_property is not None
        self.assertEqual(subject_property.property_id, int(PropertyId.SUBJECT))
        self.assertEqual(subject_property.property_type, int(PropertyId.SUBJECT.property_type))
        self.assertEqual(subject_value, "Typed subject")
        self.assertEqual(time_property.property_type, int(PropertyId.MESSAGE_DELIVERY_TIME.property_type))
        self.assertEqual(time_value, delivery_time)