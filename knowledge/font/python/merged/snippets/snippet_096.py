def test_format_interpolation_issue_includes_tuple_transitions() -> None:
    issue = GlyphInterpolationIssue(
        codepoint=ord("A"),
        character="A",
        reason="active variation tuples changed",
        before_active=(
            ActiveTupleSummary(
                tuple_index=1,
                scalar=0.5,
                peak_coords={"wght": 1.0},
                start_coords=None,
                end_coords=None,
            ),
        ),
        after_active=(
            ActiveTupleSummary(
                tuple_index=1,
                scalar=0.75,
                peak_coords={"wght": 1.0},
                start_coords=None,
                end_coords=None,
            ),
            ActiveTupleSummary(
                tuple_index=2,
                scalar=1.0,
                peak_coords={"wdth": -1.0},
                start_coords=None,
                end_coords=None,
            ),
        ),
        entered_tuple_indices=(2,),
        exited_tuple_indices=(),
        retuned_tuples=(
            TupleScalarDelta(tuple_index=1, before_scalar=0.5, after_scalar=0.75),
        ),
    )

    line = _format_interpolation_issue(issue)

    assert "U+0041 (A): active variation tuples changed" in line
    assert "before_active=1:0.5 after_active=1:0.75,2:1" in line
    assert "entered=2 exited=-" in line
    assert "retuned=1:0.5->0.75" in line