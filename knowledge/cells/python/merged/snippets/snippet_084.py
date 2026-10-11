def test_create_histogram_chart():
    """Create a histogram chart from scratch."""
    wb = Workbook()
    ws = wb.worksheets[0]
    
    # Add data - distribution of test scores
    ws.cells["A1"].value = "Score"
    
    scores = [65, 72, 78, 82, 85, 88, 90, 92, 95, 98, 100, 102, 105, 108, 110, 112, 115, 118, 120, 125,
              68, 75, 80, 84, 87, 89, 91, 93, 96, 99, 101, 104, 106, 109, 111, 113, 116, 119, 122, 128]
    
    for i, score in enumerate(scores, 2):
        ws.cells[f"A{i}"].value = score
    
    # Create histogram chart
    chart = ws.charts.add_histogram(0, 4, 20, 12)
    chart.title = "Score Distribution - Histogram"
    chart.show_legend = False
    
    # Configure histogram bins
    chart.histogram_bin_count = 10  # Divide into 10 bins
    chart.histogram_interval_closed = "r"  # Right-closed intervals
    
    # Add series
    chart.n_series.add("A2:A41", name="Scores")
    
    # Save
    output_path = examples_output_path("progcharts", "example_histogram_chart.xlsx")
    wb.save(output_path)
    assert os.path.exists(output_path)
    print(f"Created: {output_path}")
    
    # Create histogram with bin size instead of count
    wb2 = Workbook()
    ws2 = wb2.worksheets[0]
    
    # Copy data
    for i, score in enumerate(scores, 2):
        ws2.cells[f"A{i}"].value = score
    
    chart2 = ws2.charts.add_histogram(0, 4, 20, 12)
    chart2.title = "Score Distribution - Histogram (Bin Size)"
    chart2.show_legend = False
    
    # Configure histogram with bin size
    chart2.histogram_bin_size = 10  # Each bin is 10 units wide
    chart2.histogram_interval_closed = "r"
    
    chart2.n_series.add("A2:A41", name="Scores")
    
    output_path2 = examples_output_path("progcharts", "example_histogram_chart_binsize.xlsx")
    wb2.save(output_path2)
    assert os.path.exists(output_path2)
    print(f"Created: {output_path2}")