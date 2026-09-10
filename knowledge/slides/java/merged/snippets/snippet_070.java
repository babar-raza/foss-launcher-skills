@Test
    void aPartThatDeclaresADoctypeMustBeRefused() throws Exception {
        Path secret = tempDir.resolve("secret.txt");
        Files.writeString(secret, SECRET, StandardCharsets.UTF_8);
        Path poisoned = deckWithExternalEntity(secret);

        assertThatThrownBy(() -> {
            try (var pres = new Presentation(poisoned.toString())) {
                pres.getSlides().size();
            }
        }).as("opening %s, whose ppt/slides/slide1.xml declares an external entity", poisoned)
                .isInstanceOf(RuntimeException.class);
    }