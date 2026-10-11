def test_array_list_adapter_double(self):
        element = VertexElementDoublesTemplate()
        element.set_data([1.0, 2.0, 3.0, 4.0])

        data = element.data
        self.assertEqual(4, len(data))
        self.assertEqual(1.0, data[0])
        self.assertEqual(2.0, data[1])
        self.assertEqual(3.0, data[2])
        self.assertEqual(4.0, data[3])