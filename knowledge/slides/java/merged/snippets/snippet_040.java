@Test
    void testPictureFill() throws IOException {
        try (var pres = new Presentation()) {
            var slide = clear(pres);
            var shape = slide.getShapes().addAutoShape(ShapeType.RECTANGLE, 50, 50, 200, 200);
            shape.getFillFormat().setFillType(FillType.PICTURE);
            var pff = shape.getFillFormat().getPictureFillFormat();
            pff.setPictureFillMode(PictureFillMode.STRETCH);
            var img = pres.getImages().addImage(TestHelpers.createTestPng(0, 255, 0));
            pff.getPicture().setImage(img);

            try (var pres2 = saveAndReopen(pres)) {
                var ff2 = pres2.getSlides().get(0).getShapes().get(0).getFillFormat();
                assertThat(ff2.getFillType()).isEqualTo(FillType.PICTURE);
            }
        }
    }