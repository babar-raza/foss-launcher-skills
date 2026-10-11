def test_array_list_adapter_insert(self):
        element = VertexElementTemplate[float]()
        element.set_data([1.0, 3.0, 4.0])

        element.data.insert(1, 2.0)
        self.assertEqual(4, len(element.data))
        self.assertEqual(2.0, element.data[1])