def test_array_list_adapter_copy_to(self):
        element = VertexElementTemplate[float]()
        element.set_data([1.0, 2.0, 3.0, 4.0])

        array = [0.0] * 4
        element.data.copy_to(array)
        self.assertEqual(1.0, array[0])
        self.assertEqual(2.0, array[1])
        self.assertEqual(3.0, array[2])
        self.assertEqual(4.0, array[3])