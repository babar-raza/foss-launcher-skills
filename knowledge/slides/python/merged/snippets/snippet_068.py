def test_user_path_commands(self):
        from aspose.slides_foss.drawing import PointF

        with Presentation() as pres:
            slide = pres.slides[0]
            shape = slide.shapes.add_auto_shape(ShapeType.RECTANGLE, 100, 100, 200, 100)
            seq = slide.timeline.interactive_sequences.add(
                slide.shapes.add_auto_shape(ShapeType.BEVEL, 10, 10, 20, 20)
            )
            fx = seq.add_effect(shape, anim.EffectType.PATH_USER,
                                anim.EffectSubtype.NONE,
                                anim.EffectTriggerType.ON_CLICK)

            motion = fx.behaviors[0]
            assert isinstance(motion, anim.MotionEffect)

            pts1 = [PointF(0.076, 0.59)]
            motion.path.add(anim.MotionCommandPathType.LINE_TO, pts1,
                            anim.MotionPathPointsType.AUTO, True)
            pts2 = [PointF(-0.076, -0.59)]
            motion.path.add(anim.MotionCommandPathType.LINE_TO, pts2,
                            anim.MotionPathPointsType.AUTO, False)
            motion.path.add(anim.MotionCommandPathType.END, None,
                            anim.MotionPathPointsType.AUTO, False)

            assert motion.path.count == 3
            assert motion.path[0].command_type == anim.MotionCommandPathType.LINE_TO
            assert motion.path[0].is_relative is True
            assert motion.path[2].command_type == anim.MotionCommandPathType.END