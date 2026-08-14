def test_create_box_whisker_chart():
    """Create a box and whisker chart from scratch."""
    wb = Workbook()
    ws = wb.worksheets[0]
    
    # Add data - sample statistics for different groups
    ws.cells["A1"].value = "Group"
    ws.cells["B1"].value = "Q1"
    ws.cells["C1"].value = "Q2"
    ws.cells["D1"].value = "Q3"
    ws.cells["E1"].value = "Q4"
    ws.cells["F1"].value = "Q5"
    
    groups = ["Group A", "Group B", "Group C"]
    data = [
        [10, 15, 20, 25, 30],
        [12, 18, 22, 28, 35],
        [8, 14, 19, 24, 32]
    ]
    
    for i, group in enumerate(groups, 2):
        ws.cells[f"A{i}"].value = group
        for j, value in enumerate(data[i-2], 2):
            ws.cells[f"{chr(64+j)}{i}"].value = value
    
    # Create box and whisker chart
    chart = ws.charts.add_box_whisker(0, 4, 20, 12)
    chart.title = "Statistical Distribution by Group"
    chart.category_data = "B1:F1"
    chart.show_legend = True
    chart.quartile_method = "exclusive"
    chart.box_show_mean_line = False
    chart.box_show_mean_marker = True
    chart.box_show_inner_points = False
    chart.box_show_outlier_points = True
    chart.box_gap_width = 1

    # Add series
    chart.n_series.add("B2:F2", category_data="B1:F1", name="Group A")
    chart.n_series.add("B3:F3", category_data="B1:F1", name="Group B")
    chart.n_series.add("B4:F4", category_data="B1:F1", name="Group C")
    
    # Save
    output_path = examples_output_path("progcharts", "example_box_whisker_chart.xlsx")
    wb.save(output_path)
    assert os.path.exists(output_path)
    print(f"Created: {output_path}")

    # Ensure box-whisker chartEx settings are serialized
    import zipfile
    with zipfile.ZipFile(output_path) as zf:
        chart_xml = zf.read("xl/charts/chartEx1.xml").decode("utf-8")
        assert '<cx:visibility meanLine="0" meanMarker="1" nonoutliers="0" outliers="1" />' in chart_xml
        assert '<cx:catScaling gapWidth="1" />' in chart_xml