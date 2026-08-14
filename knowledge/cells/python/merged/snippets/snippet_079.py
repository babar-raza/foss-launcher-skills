def test_create_stock_chart():
    """Create a stock chart from scratch."""
    wb = Workbook()
    ws = wb.worksheets[0]
    
    # Add data for High-Low-Close stock chart
    ws.cells["A1"].value = "Date"
    ws.cells["B1"].value = "High"
    ws.cells["C1"].value = "Low"
    ws.cells["D1"].value = "Close"
    
    dates = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    highs = [105, 108, 110, 107, 112]
    lows = [100, 103, 105, 102, 108]
    closes = [103, 106, 108, 105, 110]
    
    for i, (date, high, low, close) in enumerate(zip(dates, highs, lows, closes), 2):
        ws.cells[f"A{i}"].value = date
        ws.cells[f"B{i}"].value = high
        ws.cells[f"C{i}"].value = low
        ws.cells[f"D{i}"].value = close
    
    # Create stock chart
    chart = ws.charts.add_stock(0, 4, 20, 12)
    chart.title = "Stock Price Movement"
    chart.category_data = "A2:A6"
    chart.stock_style = "high_low_close"
    chart.show_legend = False
    
    # Add series
    chart.n_series.add("B2:B6", category_data="A2:A6", name="High")
    chart.n_series.add("C2:C6", category_data="A2:A6", name="Low")
    chart.n_series.add("D2:D6", category_data="A2:A6", name="Close")
    
    # Save
    output_path = examples_output_path("progcharts", "example_stock_chart.xlsx")
    wb.save(output_path)
    assert os.path.exists(output_path)
    print(f"Created: {output_path}")