def test_same_winding_contours_enable_evenodd(self) -> None:
        contours = [
            _cw_square(0, 0, 1000, 1000),
            _cw_square(250, 250, 750, 750),
        ]
        self.assertTrue(_glyph_contours_need_even_odd(contours))