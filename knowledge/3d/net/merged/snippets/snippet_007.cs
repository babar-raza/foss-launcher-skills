[Fact]
        public void ColladaFormat_ShouldBeRegistered()
        {var format = FileFormat.GetFormatByExtension("dae");

            Assert.NotNull(format);
            Assert.Equal(".dae", format.Extension);            Assert.True(format.CanImport);
            Assert.True(format.CanExport);
        }