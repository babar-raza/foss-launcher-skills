def test_material_property_setters(self):
        from aspose.threed.shading import PbrMaterial
        from aspose.threed.utilities import Vector3

        material = PbrMaterial()

        new_albedo = Vector3(1.0, 0.5, 0.2)
        material.albedo = new_albedo
        self.assertEqual(material.albedo, new_albedo)

        material.metallic_factor = 0.8
        self.assertEqual(material.metallic_factor, 0.8)

        material.roughness_factor = 0.3
        self.assertEqual(material.roughness_factor, 0.3)

        material.transparency = 0.5
        self.assertEqual(material.transparency, 0.5)

        new_emissive = Vector3(0.1, 0.2, 0.3)
        material.emissive_color = new_emissive
        self.assertEqual(material.emissive_color, new_emissive)