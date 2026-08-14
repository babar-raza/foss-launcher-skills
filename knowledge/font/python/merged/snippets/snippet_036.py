def test_type2_invalid_subr_index():
    cs = b"".join([_enc_num(0), _enc_num(0), bytes([21]), _enc_num(0), bytes([10, 14])])
    interp = Type2Interpreter(CffIndex([]), CffIndex([]), default_width_x=500, nominal_width_x=0)
    with pytest.raises(FontParseException):
        interp.interpret(cs)