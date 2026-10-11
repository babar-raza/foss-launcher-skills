def test_obj_format_detection(self):
        obj_format = ObjFormat()
        self.assertTrue(obj_format.can_import)
        self.assertFalse(obj_format.can_export)
        self.assertEqual(obj_format.extension, "obj")
        self.assertIn("obj", obj_format.extensions)