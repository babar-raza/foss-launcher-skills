def test_type2_rlineto():
    # 0 0 rmoveto, 50 0 rlineto, endchar
    cs = b"".join(
        [
            _enc_num(0),
            _enc_num(0),
            bytes([21]),
            _enc_num(50),
            _enc_num(0),
            bytes([5, 14]),
        ]
    )
    interp = Type2Interpreter(CffIndex([]), CffIndex([]), default_width_x=500, nominal_width_x=0)
    path, width = interp.interpret(cs)
    cmds = _commands(path)
    assert width == 500
    assert isinstance(cmds[0], MoveTo)
    assert isinstance(cmds[1], LineTo)
    assert cmds[1].x == pytest.approx(50.0)
    assert isinstance(cmds[-1], ClosePath)