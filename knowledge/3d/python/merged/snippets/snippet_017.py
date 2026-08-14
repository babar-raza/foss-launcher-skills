def test_array_list_adapter_contains(self):
        element = VertexElementTemplate[float]()
        element.set_data([1.0, 2.0, 3.0, 4.0])

        self.assertTrue(element.data.contains(2.0))
        self.assertFalse(element.data.contains(5.0))