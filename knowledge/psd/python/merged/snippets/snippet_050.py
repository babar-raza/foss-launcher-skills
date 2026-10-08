def test_load_psblayerrecord_reads(self):
        stream = BytesIO(self.build_psb_layer_record_bytes())
        reader = BigEndianReader(stream, leave_open=True)

        layer = Layer.load(reader, is_large_document=True)

        assert layer.name == "Layer 1"
        assert layer.bounds == Rectangle(0, 0, 1, 1)
        assert layer.opacity == 200
        assert layer.is_visible is True