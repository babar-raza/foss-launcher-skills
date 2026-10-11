def test_page_pixel_size_snaps_integer_xps_a4_approximation(self) -> None:
        self.assertEqual(
            _page_pixel_size(595.5, 842.25, 300.0 / 72.0, preserve_fractional=True),
            (2480, 3507),
        )
        self.assertEqual(
            _page_pixel_size(841.68, 595.44, 300.0 / 72.0, preserve_fractional=True),
            (3506, 2480),
        )