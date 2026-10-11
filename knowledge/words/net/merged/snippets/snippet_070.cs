private static void ChangeFont(Font font, string fontName, double fontSize, Color color, bool bold,
            bool italic, Underline underline, int kerning, int spacing, bool doubleStrikeThrough,
            bool strikeThrough, bool allCaps, bool smallCaps, RunVerticalAlignment verticalAlignment, int localeId)
        {
            TestChartUtil.SetFontProperties(font, fontName, fontSize, kerning, spacing, bold, italic, strikeThrough,
                doubleStrikeThrough, allCaps, smallCaps, color, underline, verticalAlignment, localeId);
        }