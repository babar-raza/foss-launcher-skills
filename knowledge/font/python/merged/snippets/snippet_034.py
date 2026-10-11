def test_type2_width_extraction():
    # 50 is width; 0 0 rmoveto.
    cs = b"".join([_enc_num(50), _enc_num(0), _enc_num(0), bytes([21, 14])])
    interp = Type2Interpreter(CffIndex([]), CffIndex([]), default_width_x=500, nominal_width_x=400)
    _, width = interp.interpret(cs)
    assert width == 450