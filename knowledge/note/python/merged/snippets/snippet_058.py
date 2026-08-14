def test_save_options_is_abstract_compatibility_base(self) -> None:
        from aspose.note import SaveFormat
        from aspose.note.saving import SaveOptions

        with self.assertRaises(TypeError):
            SaveOptions(SaveFormat.Pdf)