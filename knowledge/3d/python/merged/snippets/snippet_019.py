def test_array_list_adapter_clear(self):
        element = VertexElementTemplate[float]()
        element.set_data([1.0, 2.0, 3.0, 4.0])

        element.data.clear()
        self.assertEqual(0, len(element.data))