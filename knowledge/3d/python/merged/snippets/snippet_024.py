def test_array_list_adapter_to_array(self):
        element = VertexElementTemplate[float]()
        element.set_data([1.0, 2.0, 3.0, 4.0])

        arr = element.data.to_array()
        self.assertEqual(4, len(arr))
        self.assertEqual(1.0, arr[0])
        self.assertEqual(2.0, arr[1])
        self.assertEqual(3.0, arr[2])
        self.assertEqual(4.0, arr[3])