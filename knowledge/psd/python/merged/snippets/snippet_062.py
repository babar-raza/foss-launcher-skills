def test_load_nullstream_throws(self):
        with pytest.raises(ArgumentNullException):
            PsdImage.load(None)