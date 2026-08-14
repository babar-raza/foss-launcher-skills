private static void CheckLegendEntryFont(Document document, int shapeIndex, int entryIndex,
            string expectedFontName, double expectedFontSize, Color expectedColor, bool expectedBold,
            bool expectedItalic, Underline expectedUnderline)
        {
            Chart chart = document.FirstSection.Body.Shapes[shapeIndex].Chart;
            ChartLegendEntry legendEntry = chart.Legend.LegendEntries[entryIndex];

            CheckFont(legendEntry.Font, expectedFontName, expectedFontSize, expectedColor,
                expectedBold, expectedItalic, expectedUnderline);
        }