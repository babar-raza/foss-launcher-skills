def test_textrun_does_not_expose_run_boundaries(self) -> None:
        from aspose.note import TextRun

        run = TextRun(Text="segment")

        self.assertFalse(hasattr(run, "Start"))
        self.assertFalse(hasattr(run, "End"))