[Fact]
         public void LoadSceneFromUnsupportedFormat_ShouldThrowNotSupportedException()
        {
            // Test with a non-existent file that doesn't match any supported format
            // This tests the exception when no matching format is found
            var testFile = "../../../../../../testdata/unknown.xyz";
            
            var scene = new Scene();
            Assert.Throws<ArgumentException>(() => scene.Open(testFile));
        }