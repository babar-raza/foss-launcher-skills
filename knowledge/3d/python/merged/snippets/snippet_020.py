def test_array_list_adapter_index_of(self):
        element = VertexElementTemplate[float]()
        element.set_data([1.0, 2.0, 3.0, 4.0])

        self.assertEqual(0, element.data.index_of(1.0))
        self.assertEqual(2, element.data.index_of(3.0))
        self.assertEqual(-1, element.data.index_of(10.0))