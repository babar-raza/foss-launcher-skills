def test_motion_path_clear(self):
        with Presentation() as pres:
            slide = pres.slides[0]
            shape = slide.shapes.add_auto_shape(ShapeType.RECTANGLE, 10, 10, 100, 50)
            seq = slide.timeline.interactive_sequences.add(
                slide.shapes.add_auto_shape(ShapeType.BEVEL, 10, 10, 20, 20)
            )
            fx = seq.add_effect(shape, anim.EffectType.PATH_USER,
                                anim.EffectSubtype.NONE,
                                anim.EffectTriggerType.ON_CLICK)
            motion = fx.behaviors[0]
            motion.path.add(anim.MotionCommandPathType.LINE_TO, [],
                            anim.MotionPathPointsType.AUTO, True)
            assert motion.path.count == 1
            motion.path.clear()
            assert motion.path.count == 0