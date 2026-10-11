[Test, Ignore("TestDefects")]
        public void TestCloningChartTitle()
        {
            Document doc = TestUtil.Open(@"Model\Charts\TestJira16069.docx");
            Document clone = doc.Clone();
            ChartTitle title = clone.FirstSection.Body.Shapes[0].Chart.Title;
            Assert.Fail("The mDocument field of the 'title' object has wrong value, it should be equals to 'clone'.");
        }