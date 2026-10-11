private static void assertSceneIsComplete(Path pptx) throws Exception {
        try (PptxPackage pkg = PptxPackage.open(pptx)) {
            List<Element> scenes = PackageAssertions.selectNodes(
                    pkg, "ppt/slides/slide1.xml", "//p:sp/p:spPr/a:scene3d");
            assertThat(scenes).as("a:scene3d elements in %s", pptx).hasSize(1);
            PackageAssertions.assertChildrenInSchemaOrder(
                    scenes.get(0), "a:camera", "a:lightRig", "a:backdrop", "a:extLst");
            assertThat(PackageAssertions.childNames(scenes.get(0)))
                    .as("a:scene3d requires both a camera and a light rig, in %s", pptx)
                    .contains("a:camera", "a:lightRig");

            Element camera = PackageAssertions.selectNodes(
                    pkg, "ppt/slides/slide1.xml", "//a:scene3d/a:camera").get(0);
            assertThat(camera.hasAttribute("prst"))
                    .as("a:camera/@prst is required, in %s", pptx)
                    .isTrue();

            Element lightRig = PackageAssertions.selectNodes(
                    pkg, "ppt/slides/slide1.xml", "//a:scene3d/a:lightRig").get(0);
            assertThat(lightRig.hasAttribute("rig"))
                    .as("a:lightRig/@rig is required, in %s", pptx)
                    .isTrue();
            assertThat(lightRig.hasAttribute("dir"))
                    .as("a:lightRig/@dir is required, in %s", pptx)
                    .isTrue();
        }
    }