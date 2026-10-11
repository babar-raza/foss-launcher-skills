def test_baseline_map(self):
        with EnvGuard(BASELINE_MAP="ps/images=/tmp/baselines"):
            baseline = baseline_path_for(Path("testdata/ps/images/foo.png"), ".eps")
            self.assertEqual(baseline.as_posix(), "/tmp/baselines/foo.eps")