def test_a_scene_is_never_written_half_populated(produced, shape_on_blank_slide):
    """Setting only the camera must still produce a complete `<a:scene3d>`."""
    pres, shape = shape_on_blank_slide()
    shape.three_d_format.camera.camera_type = CameraPresetType.ORTHOGRAPHIC_FRONT
    pkg = produced(pres)

    scene = pkg.find_one(SLIDE, "//a:scene3d")
    present = child_names(scene)
    assert "a:lightRig" in present, (
        "<a:scene3d> requires both <a:camera> and <a:lightRig>; only %r was "
        "written, which no strict consumer will accept" % present
    )