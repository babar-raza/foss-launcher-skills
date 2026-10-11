@ParameterizedTest(name = "{0}")
    @EnumSource(LightRigPresetType.class)
    void aLightRigMustBeWrittenWithTheCameraTheSchemaRequires(LightRigPresetType lightRig)
            throws Exception {
        Path out = tempDir.resolve("lightrig-"
                + lightRig.name().toLowerCase(Locale.ROOT) + ".pptx");
        try (var pres = new Presentation()) {
            IAutoShape shape = pres.getSlides().get(0).getShapes()
                    .addAutoShape(ShapeType.RECTANGLE, 50, 50, 200, 100);
            shape.getThreeDFormat().getLightRig().setLightType(lightRig);
            pres.save(out.toString(), SaveFormat.PPTX);
        }
        assertSceneIsComplete(out);
    }