def test_add_path_effect(self):
        with Presentation() as pres:
            slide = pres.slides[0]
            shape = slide.shapes.add_auto_shape(ShapeType.RECTANGLE, 10, 10, 100, 50)
            effect = slide.timeline.main_sequence.add_effect(
                shape, anim.EffectType.PATH_FOOTBALL,
                anim.EffectSubtype.NONE,
                anim.EffectTriggerType.ON_CLICK,
            )

            assert effect.type == anim.EffectType.PATH_FOOTBALL
            assert effect.preset_class_type == anim.EffectPresetClassType.PATH