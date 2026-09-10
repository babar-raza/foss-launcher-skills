def test_all_extrusion_properties_exist(self):
        bp = anim.BehaviorProperty()
        assert bp.extrusion_on.value == 'extrusion.on'
        assert bp.extrusion_color_mode.value == 'extrusion.colormode'