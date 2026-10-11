[Test]
        public void TestFont()
        {
            const string fileName = @"Model\Charts\TestDataTableFont";
            Document doc = TestUtil.Open(fileName, LoadFormat.Docx);
            ShapeCollection shapes = doc.FirstSection.Body.Shapes;

            Assert.That(shapes[0].Chart.DataTable.Show, Is.True);

            Font font1 = shapes[0].Chart.DataTable.Font;
            Font font2 = shapes[1].Chart.DataTable.Font;
            Font font3 = shapes[2].Chart.DataTable.Font;
            Font font4 = shapes[3].Chart.DataTable.Font;

            CheckFont(font1, "Arial", 11.5, Color.FromArgb(0x2E, 0x75, 0xB5), Color.Empty, true, true,
                Underline.DottedHeavy, 7, 1, false, false, false, true, RunVerticalAlignment.Subscript, 1024);
            CheckFont(font2, "Calibri", 10, Color.FromArgb(0x59, 0x59, 0x59), Color.Empty, false, true,
                Underline.None, 0, 0, true, false, true, false, RunVerticalAlignment.Baseline, 1024);
            // Data table of the 3rd chart uses chart space font.
            CheckFont(font3, "Times New Roman", 14, Color.Empty, Color.Empty, false, true,
                Underline.None, 0, 0.5, false, true, true, false, RunVerticalAlignment.Superscript, 1024);
            // Data table of the 4th chart uses font defaults.
            CheckFont(font4, "Calibri", 10, Color.Empty, Color.Empty, false, false,
                Underline.None, 12, 0, false, false, false, false, RunVerticalAlignment.Baseline, 1024);

            ChangeFont(font1, "Courier New", 11, Color.DarkRed, true, false,
                Underline.Double, 10, 3, true, false, true, false, RunVerticalAlignment.Superscript, 1049);
            font1.HighlightColor = Color.Cyan;

            font2.ClearFormatting();

            ChangeFont(font3, "Verdana", 12, Color.Green, true, false,
                Underline.None, 12, 4, false, true, false, true, RunVerticalAlignment.Baseline, 1049);

            ChangeFont(font4, "Times New Roman", 14, Color.Red, false, true,
                Underline.Dotted, 3, 3, false, true, true, false, RunVerticalAlignment.Subscript, 1049);

            CheckFont(font1, "Courier New", 11, DrColor.DarkRed.ToNativeColor(), DrColor.Cyan.ToNativeColor(),
                true, false, Underline.Double, 10, 3, true, false, true, false, RunVerticalAlignment.Superscript, 1049);
            CheckFont(font2, "Calibri", 10, Color.Empty, Color.Empty, false, false,
                Underline.None, 12, 0, false, false, false, false, RunVerticalAlignment.Baseline, 1024);
            CheckFont(font3, "Verdana", 12, DrColor.Green.ToNativeColor(), Color.Empty, true, false,
                Underline.None, 12, 4, false, true, false, true, RunVerticalAlignment.Baseline, 1049);
            CheckFont(font4, "Times New Roman", 14, DrColor.Red.ToNativeColor(), Color.Empty,
                false, true, Underline.Dotted, 3, 3, false, true, true, false, RunVerticalAlignment.Subscript, 1049);

            doc = TestUtil.SaveOpen(doc, fileName, UnifiedScenario.Docx2Docx | UnifiedScenario.ExportOnly);
            shapes = doc.FirstSection.Body.Shapes;
            font1 = shapes[0].Chart.DataTable.Font;
            font2 = shapes[1].Chart.DataTable.Font;
            font3 = shapes[2].Chart.DataTable.Font;
            font4 = shapes[3].Chart.DataTable.Font;

            CheckFont(font1, "Courier New", 11, DrColor.DarkRed.ToNativeColor(), DrColor.Cyan.ToNativeColor(),
                true, false, Underline.Double, 10, 3, true, false, true, false, RunVerticalAlignment.Superscript, 1049);
            CheckFont(font2, "Calibri", 10, Color.Empty, Color.Empty, false, false,
                Underline.None, 12, 0, false, false, false, false, RunVerticalAlignment.Baseline, 1024);
            CheckFont(font3, "Verdana", 12, DrColor.Green.ToNativeColor(), Color.Empty, true, false,
                Underline.None, 12, 4, false, true, false, true, RunVerticalAlignment.Baseline, 1049);
            CheckFont(font4, "Times New Roman", 14, DrColor.Red.ToNativeColor(), Color.Empty,
                false, true, Underline.Dotted, 3, 3, false, true, true, false, RunVerticalAlignment.Subscript, 1049);
        }