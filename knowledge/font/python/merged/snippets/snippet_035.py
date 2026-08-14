def test_type2_subr_inline_equivalent():
    # Main: 0 0 rmoveto, callsubr(0), endchar. Subr0: 50 0 rlineto, return
    main = b"".join([_enc_num(0), _enc_num(0), bytes([21]), _enc_num(-107), bytes([10, 14])])
    subr0 = b"".join([_enc_num(50), _enc_num(0), bytes([5, 11])])
    interp_subr = Type2Interpreter(CffIndex([]), CffIndex([subr0]), default_width_x=500, nominal_width_x=0)
    path_subr, _ = interp_subr.interpret(main)

    inlined = b"".join([_enc_num(0), _enc_num(0), bytes([21]), _enc_num(50), _enc_num(0), bytes([5, 14])])
    interp_inline = Type2Interpreter(CffIndex([]), CffIndex([]), default_width_x=500, nominal_width_x=0)
    path_inline, _ = interp_inline.interpret(inlined)
    assert _signature(path_subr) == _signature(path_inline)