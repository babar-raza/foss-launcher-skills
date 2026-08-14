def test_array_list_adapter_int(self):
        element = VertexElementIntsTemplate()
        element.set_data([1, 2, 3, 4])

        data = element.data
        self.assertEqual(4, len(data))
        self.assertEqual(1, data[0])
        self.assertEqual(2, data[1])
        self.assertEqual(3, data[2])
        self.assertEqual(4, data[3])