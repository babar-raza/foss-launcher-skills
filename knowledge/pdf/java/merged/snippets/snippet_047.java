@Test
    void existingAnnotationCtor_stillWorks() {
        // Regression check: the original (Annotation) ctor is untouched.
        Border border = new Border((Annotation) null);
        assertNotNull(border);
        assertEquals(1.0, border.getWidth(), 1e-6);
    }