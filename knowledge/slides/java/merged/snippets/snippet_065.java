@ParameterizedTest(name = "{0}")
    @EnumSource(CameraPresetType.class)
    void aCameraMustBeWrittenWithTheLightRigTheSchemaRequires(CameraPresetType camera)
            throws Exception {
        Path out = tempDir.resolve("camera-" + camera.name().toLowerCase(Locale.ROOT) + ".pptx");
        try (var pres = new Presentation()) {
            IAutoShape shape = pres.getSlides().get(0).getShapes()
                    .addAutoShape(ShapeType.RECTANGLE, 50, 50, 200, 100);
            shape.getThreeDFormat().getCamera().setCameraType(camera);
            pres.save(out.toString(), SaveFormat.PPTX);
        }
        assertSceneIsComplete(out);
    }