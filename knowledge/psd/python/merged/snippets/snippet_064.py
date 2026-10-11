def test_load_invalidsignature_throws(self):
        with io.BytesIO(self._build_header_bytes(PsdHeader.PSD_VERSION)) as stream:
            with BigEndianReader(stream, leave_open=True) as reader:
                stream.seek(0)
                stream.write(b"B")
                stream.seek(0)

                with pytest.raises(PsdLoadException):
                    PsdHeader.load(reader)