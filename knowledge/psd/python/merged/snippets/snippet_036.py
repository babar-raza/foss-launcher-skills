def test_load_resources_reads_blocks(self):
        resources_payload = self.build_resources_payload(
            (ImageResourceIds.GLOBAL_ANGLE, "glba", bytes([0x00, 0x00, 0x00, 0x2D])),
            (ImageResourceIds.ICC_PROFILE, "icc", bytes([0x49, 0x43, 0x43, 0x50])),
            (ImageResourceIds.ICC_UNTAGGED_PROFILE, "", bytes([0x01])),
        )
        stream = io.BytesIO(resources_payload)
        reader = BigEndianReader(stream, leave_open=True)

        resources = []
        stream_length = len(stream.getvalue())
        while reader.position < stream_length:
            resource = UnknownResource.load(reader, stream_length)
            assert resource is not None
            resources.append(resource)

        assert len(resources) == 3
        assert resources[0].resource_id == ImageResourceIds.GLOBAL_ANGLE
        assert resources[0].data == bytes([0x00, 0x00, 0x00, 0x2D])
        assert resources[1].resource_id == ImageResourceIds.ICC_PROFILE
        assert resources[1].data == bytes([0x49, 0x43, 0x43, 0x50])
        assert resources[2].resource_id == ImageResourceIds.ICC_UNTAGGED_PROFILE
        assert resources[2].data == bytes([0x01])