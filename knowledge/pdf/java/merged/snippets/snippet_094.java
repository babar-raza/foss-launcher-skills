private static byte[] fixtureTtf() {
        Map<Character, Integer> g = new LinkedHashMap<>();
        g.put('A', 700);
        return MinimalTtf.build("TestFont", g);
    }