@Test
    void textShowOrigin_isIncluded() {
        Page.ContentBBoxCalculator calc = new Page.ContentBBoxCalculator();
        calc.visit(new BT());
        calc.visit(new SetTextMatrix(new Matrix(1, 0, 0, 1, 100, 700))); // origin (100,700)
        calc.visit(new ShowText("hi"));
        calc.visit(new ET());
        Rectangle r = calc.toRectangle();
        assertNotNull(r);
        // The origin point lands in the bbox; min == max == origin
        assertEquals(100, r.getLLX(), 1e-3);
        assertEquals(700, r.getLLY(), 1e-3);
    }