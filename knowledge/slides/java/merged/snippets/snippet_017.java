private Path writeDeckWithPicture(String fileName, byte[] imageBytes) throws IOException {
        Path out = tempDir.resolve(fileName);
        try (var pres = new Presentation()) {
            IPPImage image = pres.getImages().addImage(imageBytes);
            ISlide slide = pres.getSlides().get(0);
            slide.getShapes().addPictureFrame(ShapeType.RECTANGLE, 50, 50, 200, 150, image);
            pres.save(out.toString(), SaveFormat.PPTX);
        }
        return out;
    }