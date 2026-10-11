def test_collada_format_can_export(self):
        from aspose.threed.formats.collada.ColladaFormat import ColladaFormat

        collada_format = ColladaFormat()
        self.assertTrue(collada_format.can_export)