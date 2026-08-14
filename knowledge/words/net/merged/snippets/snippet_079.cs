[Test]
        public void TestLegendEntryFormat()
        {
            Document doc = TestUtil.Open(@"Model\Charts\TestLegendEntryFormat.docx");

            CheckLegendEntryFont(doc, 0, 0, "Arial", 11, Color.FromArgb(0x80, 0, 0), true, true, Underline.Single);
            CheckLegendEntryFont(doc, 0, 1, "Calibri Light", 9, Color.FromArgb(0, 0, 0x80), true, false, Underline.Dash);
            CheckLegendEntryFont(doc, 0, 2, "Calibri Light", 7, Color.FromArgb(0, 0, 0x80), true, false, Underline.Dash);
            CheckLegendEntryFont(doc, 0, 3, "Times New Roman", 9, Color.FromArgb(0, 0, 0x80), true, false, Underline.Dash);
            CheckLegendEntryFont(doc, 0, 4, "Calibri Light", 9, Color.FromArgb(0, 0x80, 0), true, false, Underline.Dash);

            CheckLegendEntryFont(doc, 1, 0, "Calibri Light", 9, Color.FromArgb(0, 0, 0x80), true, false, Underline.Dash);
            CheckLegendEntryFont(doc, 1, 1, "Calibri Light", 9, Color.FromArgb(0, 0, 0x80), true, false, Underline.Dash);
            CheckLegendEntryFont(doc, 1, 2, "Calibri Light", 7, Color.FromArgb(0, 0, 0x80), true, false, Underline.Dash);
            CheckLegendEntryFont(doc, 1, 3, "Times New Roman", 9, Color.FromArgb(0, 0, 0x80), true, false, Underline.Dash);
            CheckLegendEntryFont(doc, 1, 4, "Calibri Light", 9, Color.FromArgb(0, 0x80, 0), true, false, Underline.Dash);

            CheckLegendEntryFont(doc, 2, 0, "Calibri Light", 9, Color.FromArgb(0, 0, 0x80), true, false, Underline.Dash);
            CheckLegendEntryFont(doc, 2, 1, "Calibri Light", 9, Color.FromArgb(0, 0, 0x80), true, false, Underline.Dash);
            CheckLegendEntryFont(doc, 2, 2, "Calibri Light", 7, Color.FromArgb(0, 0, 0x80), true, false, Underline.Dash);
            CheckLegendEntryFont(doc, 2, 3, "Times New Roman", 9, Color.FromArgb(0, 0, 0x80), true, false, Underline.Dash);
            CheckLegendEntryFont(doc, 2, 4, "Calibri Light", 9, Color.FromArgb(0, 0x80, 0), true, false, Underline.Dash);

            CheckLegendEntryFont(doc, 3, 0, "Calibri", 10, Color.Empty, false, false, Underline.None);
            CheckLegendEntryFont(doc, 3, 1, "Calibri", 10, Color.Empty, false, false, Underline.None);
            CheckLegendEntryFont(doc, 3, 2, "Calibri", 7, Color.Empty, false, false, Underline.None);
            CheckLegendEntryFont(doc, 3, 3, "Times New Roman", 10, Color.Empty, false, false, Underline.None);
            CheckLegendEntryFont(doc, 3, 4, "Calibri", 10, Color.FromArgb(0, 0x80, 0), false, false, Underline.None);

            CheckLegendEntryFont(doc, 4, 0, "Calibri Light", 12, Color.FromArgb(0, 0, 0x80), true, false, Underline.Dash);
            CheckLegendEntryFont(doc, 4, 1, "Calibri Light", 9, Color.FromArgb(0, 0, 0x80), true, false, Underline.Dash);
            CheckLegendEntryFont(doc, 4, 2, "Calibri Light", 7, Color.FromArgb(0, 0, 0x80), true, false, Underline.Dash);
            CheckLegendEntryFont(doc, 4, 3, "Times New Roman", 9, Color.FromArgb(0, 0, 0x80), true, false, Underline.Dash);
            CheckLegendEntryFont(doc, 4, 4, "Calibri Light", 9, Color.FromArgb(0, 0x80, 0), true, false, Underline.Dash);

            CheckLegendEntryFont(doc, 5, 0, "Arial", 9, Color.FromArgb(0, 0, 0x80), true, false, Underline.Dash);
            CheckLegendEntryFont(doc, 5, 1, "Calibri Light", 9, Color.FromArgb(0, 0, 0x80), true, false, Underline.Dash);
            CheckLegendEntryFont(doc, 5, 2, "Calibri Light", 7, Color.FromArgb(0, 0, 0x80), true, false, Underline.Dash);
            CheckLegendEntryFont(doc, 5, 3, "Times New Roman", 9, Color.FromArgb(0, 0, 0x80), true, false, Underline.Dash);
            CheckLegendEntryFont(doc, 5, 4, "Calibri Light", 9, Color.FromArgb(0, 0x80, 0), true, false, Underline.Dash);

            CheckLegendEntryFont(doc, 6, 0, "Calibri Light", 9, Color.FromArgb(0x80, 0, 0), true, false, Underline.Dash);
            CheckLegendEntryFont(doc, 6, 1, "Calibri Light", 9, Color.FromArgb(0, 0, 0x80), true, false, Underline.Dash);
            CheckLegendEntryFont(doc, 6, 2, "Calibri Light", 7, Color.FromArgb(0, 0, 0x80), true, false, Underline.Dash);
            CheckLegendEntryFont(doc, 6, 3, "Times New Roman", 9, Color.FromArgb(0, 0, 0x80), true, false, Underline.Dash);
            CheckLegendEntryFont(doc, 6, 4, "Calibri Light", 9, Color.FromArgb(0, 0x80, 0), true, false, Underline.Dash);
        }