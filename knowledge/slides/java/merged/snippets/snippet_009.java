static Stream<Arguments> effects() {
        return Stream.of(
                effect("blur", "a:blur", c -> c.enableBlurEffect(), List.of(), List.of()),
                effect("fill overlay", "a:fillOverlay", c -> c.enableFillOverlayEffect(),
                        List.of("blend"), FILL_CHOICE),
                effect("glow", "a:glow", c -> c.enableGlowEffect(), List.of(), COLOR_CHOICE),
                effect("inner shadow", "a:innerShdw", c -> c.enableInnerShadowEffect(),
                        List.of(), COLOR_CHOICE),
                effect("outer shadow", "a:outerShdw", c -> c.enableOuterShadowEffect(),
                        List.of(), COLOR_CHOICE),
                effect("preset shadow", "a:prstShdw", c -> c.enablePresetShadowEffect(),
                        List.of("prst"), COLOR_CHOICE),
                effect("reflection", "a:reflection", c -> c.enableReflectionEffect(),
                        List.of(), List.of()),
                effect("soft edge", "a:softEdge", c -> c.enableSoftEdgeEffect(),
                        List.of("rad"), List.of()));
    }