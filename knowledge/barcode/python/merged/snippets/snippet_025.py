def test_code128_auto_encodes_single_space_via_code_set_b() -> None:
    """A lone space should be encoded through Code Set B (START_B), not Code Set A.

    A single space is representable in both Code Set A and Code Set B; the standards-correct
    minimization selects Code Set B. AUTO must therefore produce the same symbol as an explicit
    Code Set B request and begin with the START_B pattern (not START_A).
    """
    encoder = Code128Encoder()
    auto_symbol = encoder.encode(_build_payload(" ", encode_mode=Code128EncodeMode.AUTO))
    code_b_symbol = encoder.encode(_build_payload(" ", encode_mode=Code128EncodeMode.CODE_B))

    auto_rows = tuple("".join(str(module) for module in row) for row in auto_symbol.matrix.modules)
    code_b_rows = tuple("".join(str(module) for module in row) for row in code_b_symbol.matrix.modules)

    assert auto_rows == code_b_rows
    assert auto_rows[0].startswith(START_B_PATTERN)
    assert not auto_rows[0].startswith(START_A_PATTERN)
    assert auto_symbol.matrix.height == 1