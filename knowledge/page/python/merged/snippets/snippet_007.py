def test_opposite_winding_contours_keep_nonzero(self) -> None:
        contours = [
            _cw_square(0, 0, 1000, 1000),
            _ccw_square(250, 250, 750, 750),
        ]
        self.assertFalse(_glyph_contours_need_even_odd(contours))