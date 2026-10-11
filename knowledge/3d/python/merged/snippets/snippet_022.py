def test_array_list_adapter_remove_at(self):
        element = VertexElementTemplate[float]()
        element.set_data([1.0, 2.0, 3.0, 4.0])

        element.data.remove_at(1)
        self.assertEqual(3, len(element.data))
        self.assertFalse(element.data.contains(2.0))