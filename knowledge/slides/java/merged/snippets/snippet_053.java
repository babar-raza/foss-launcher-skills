static Stream<LineDashStyle> dashStyles() {
        return Stream.of(
                LineDashStyle.SOLID, LineDashStyle.DASH,
                LineDashStyle.DOT, LineDashStyle.DASH_DOT
        );
    }