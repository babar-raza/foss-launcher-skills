def test_format_compat_issue_includes_geometry_notes() -> None:
    issue = GlyphCompatibilityIssue(
        codepoint=ord("A"),
        character="A",
        reason="point count differs",
        geometry_notes=("line segments 0->1", "quadratic segments 1->0"),
        before_signature=("M", "Q"),
        after_signature=("M", "L"),
        before_stats=GlyphOutlineStats(
            command_count=2,
            point_count=3,
            contour_count=1,
            advance_width=500,
            line_count=0,
            quadratic_count=1,
            cubic_count=0,
            control_point_count=1,
            closed_contour_count=0,
            open_contour_count=1,
            start_point=(0.0, 0.0),
            end_point=(30.0, 40.0),
            bbox=(0.0, 0.0, 30.0, 40.0),
        ),
        after_stats=GlyphOutlineStats(
            command_count=2,
            point_count=2,
            contour_count=1,
            advance_width=500,
            line_count=1,
            quadratic_count=0,
            cubic_count=0,
            control_point_count=0,
            closed_contour_count=0,
            open_contour_count=1,
            start_point=(0.0, 0.0),
            end_point=(30.0, 40.0),
            bbox=(0.0, 0.0, 30.0, 40.0),
        ),
    )

    line = _format_compat_issue(issue)

    assert "U+0041 (A): point count differs" in line
    assert "geometry_notes=line segments 0->1; quadratic segments 1->0" in line