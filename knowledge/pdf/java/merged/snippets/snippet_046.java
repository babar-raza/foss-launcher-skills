@Test
    void ctor_nullOption_throws() {
        assertThrows(IllegalArgumentException.class, () -> new Border((RadioButtonOptionField) null));
    }