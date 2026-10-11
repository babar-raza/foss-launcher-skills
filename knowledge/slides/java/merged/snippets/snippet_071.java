@Test
    void anExternalEntityMustNotDiscloseTheFileItNames() throws Exception {
        Path secret = tempDir.resolve("secret.txt");
        Files.writeString(secret, SECRET, StandardCharsets.UTF_8);
        Path poisoned = deckWithExternalEntity(secret);

        StringBuilder everythingRead = new StringBuilder();
        try (var pres = new Presentation(poisoned.toString())) {
            for (int s = 0; s < pres.getSlides().size(); s++) {
                ISlide slide = pres.getSlides().get(s);
                for (int i = 0; i < slide.getShapes().size(); i++) {
                    IShape shape = slide.getShapes().get(i);
                    if (shape instanceof IAutoShape autoShape && autoShape.getTextFrame() != null) {
                        everythingRead.append(autoShape.getTextFrame().getText());
                    }
                }
            }
        } catch (RuntimeException expected) {
            everythingRead.append(String.valueOf(expected.getMessage()));
        }

        assertThat(everythingRead.toString())
                .as("everything %s yielded; it declared an external entity naming a file whose "
                        + "contents are %s", poisoned, SECRET)
                .doesNotContain(SECRET);
    }