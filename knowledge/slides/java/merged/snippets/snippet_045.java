@Test
    void testMultipleImages() throws IOException {
        try (Presentation pres = new Presentation()) {
            int[][] colors = {{255, 0, 0}, {0, 255, 0}, {0, 0, 255}};
            for (int[] c : colors) {
                pres.getImages().addImage(createTestPng(c[0], c[1], c[2]));
            }
            assertThat(pres.getImages().size()).isGreaterThanOrEqualTo(3);

            List<IPPImage> imgs = new ArrayList<>();
            for (IPPImage img : pres.getImages()) {
                imgs.add(img);
            }
            assertThat(imgs).hasSizeGreaterThanOrEqualTo(3);
        }
    }