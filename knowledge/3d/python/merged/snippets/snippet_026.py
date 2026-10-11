def test_array_list_adapter_iterate(self):
        element = VertexElementTemplate[float]()
        element.set_data([1.0, 2.0, 3.0, 4.0])

        result = list(element.data)
        self.assertEqual([1.0, 2.0, 3.0, 4.0], result)