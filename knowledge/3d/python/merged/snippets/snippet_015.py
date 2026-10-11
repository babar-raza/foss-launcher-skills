def test_array_list_adapter_modify(self):
        element = VertexElementTemplate[float]()
        element.set_data([1.0, 2.0, 3.0, 4.0])

        data = element.data
        data[1] = 10.0
        self.assertEqual(10.0, data[1])
        self.assertEqual(10.0, element.data[1])