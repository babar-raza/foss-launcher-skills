[Test]
        public void TestGridLinesInWord2016Chart()
        {
            Document doc = TestUtil.Open(@"Model\Charts\Word2016Charts\Pareto.docx");
            CheckGridlines(doc, @"Model\Charts\Word2016Charts\Pareto{0}.docx");
        }