def test_type2_stack_limit():
    cs = (bytes([139]) * 514) + bytes([14])
    interp = Type2Interpreter(CffIndex([]), CffIndex([]), default_width_x=500, nominal_width_x=0)
    with pytest.raises(FontParseException):
        interp.interpret(cs)