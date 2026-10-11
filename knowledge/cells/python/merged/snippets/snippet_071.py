def test_create_line_chart():
    """Create a line chart from scratch."""
    wb = Workbook()
    ws = wb.worksheets[0]
    
    # Add data
    ws.cells["A1"].value = "Month"
    ws.cells["B1"].value = "Sales"
    ws.cells["C1"].value = "Expenses"
    
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
    sales = [100, 150, 120, 180, 200, 170]
    expenses = [80, 90, 85, 100, 110, 95]
    
    for i, (month, sale, expense) in enumerate(zip(months, sales, expenses), 2):
        ws.cells[f"A{i}"].value = month
        ws.cells[f"B{i}"].value = sale
        ws.cells[f"C{i}"].value = expense
    
    # Create line chart
    chart = ws.charts.add_line(0, 4, 20, 12)
    chart.title = "Monthly Sales and Expenses"
    chart.category_data = "A2:A7"
    chart.show_legend = True
    chart.legend_position = "right"
    
    # Add series
    chart.n_series.add("B2:B7", category_data="A2:A7", name="Sales")
    chart.n_series.add("C2:C7", category_data="A2:A7", name="Expenses")
    
    # Save
    output_path = examples_output_path("progcharts", "example_line_chart.xlsx")
    wb.save(output_path)
    assert os.path.exists(output_path)
    print(f"Created: {output_path}")