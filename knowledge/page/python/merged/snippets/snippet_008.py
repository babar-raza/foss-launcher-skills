def test_single_contour_keeps_nonzero(self) -> None:
        contours = [_cw_square(0, 0, 1000, 1000)]
        self.assertFalse(_glyph_contours_need_even_odd(contours))