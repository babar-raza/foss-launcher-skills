def test_image_documents_to_all_formats(self):
        for filename in IMAGE_FILES:
            stem = Path(filename).stem
            self.convert_to_all_formats(filename, f"Images.{stem}")