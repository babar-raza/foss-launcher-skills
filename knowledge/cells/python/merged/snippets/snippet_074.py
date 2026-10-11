def test_create_area_chart():
    """Create an area chart from scratch."""
    wb = Workbook()
    ws = wb.worksheets[0]
    
    # Add data
    ws.cells["A1"].value = "Year"
    ws.cells["B1"].value = "Revenue"
    ws.cells["C1"].value = "Profit"
    
    years = ["2019", "2020", "2021", "2022", "2023"]
    revenue = [1000, 1200, 1500, 1800, 2000]
    profit = [200, 250, 350, 400, 500]
    
    for i, (year, rev, prof) in enumerate(zip(years, revenue, profit), 2):
        ws.cells[f"A{i}"].value = year
        ws.cells[f"B{i}"].value = rev
        ws.cells[f"C{i}"].value = prof
    
    # Create area chart
    chart = ws.charts.add_area(0, 4, 20, 12)
    chart.title = "Revenue and Profit Trend"
    chart.category_data = "A2:A6"
    chart.grouping = "standard"
    chart.show_legend = True
    
    # Add series
    chart.n_series.add("B2:B6", category_data="A2:A6", name="Revenue")
    chart.n_series.add("C2:C6", category_data="A2:A6", name="Profit")
    
    # Save
    output_path = examples_output_path("progcharts", "example_area_chart.xlsx")
    wb.save(output_path)
    assert os.path.exists(output_path)
    print(f"Created: {output_path}")