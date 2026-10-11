def test_array_list_adapter_add(self):
        element = VertexElementTemplate[float]()
        element.data.add(1.0)
        element.data.add(2.0)
        element.data.add(3.0)

        self.assertEqual(3, len(element.data))
        self.assertEqual(1.0, element.data[0])
        self.assertEqual(2.0, element.data[1])
        self.assertEqual(3.0, element.data[2])