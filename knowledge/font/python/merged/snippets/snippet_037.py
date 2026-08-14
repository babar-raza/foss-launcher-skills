def test_type2_subr_depth_limit():
    # Subr0 recursively calls itself.
    subr0 = b"".join([_enc_num(-107), bytes([10, 11])])
    main = b"".join([_enc_num(-107), bytes([10, 14])])
    interp = Type2Interpreter(CffIndex([]), CffIndex([subr0]), default_width_x=500, nominal_width_x=0)
    with pytest.raises(FontParseException):
        interp.interpret(main)