@Test
    void classSyntaxDataValueVsDataGroup() throws Exception {
        SomResolver.Context ctx = new SomResolver.Context();
        ctx.data = data();
        // Receipt has Detail (group) x3 + Total_Price (value)
        List<XfaNode> groups = som.resolveNodes("$data.Receipt.#dataGroup[*]", ctx);
        assertEquals(3, groups.size());
        List<XfaNode> values = som.resolveNodes("$data.Receipt.#dataValue[*]", ctx);
        assertEquals(1, values.size());
        assertEquals("Total_Price", values.get(0).getElementName());
    }