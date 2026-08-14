def test_create_pie_chart():
    """Create a pie chart from scratch."""
    wb = Workbook()
    ws = wb.worksheets[0]
    
    # Add data
    ws.cells["A1"].value = "Category"
    ws.cells["B1"].value = "Value"
    
    categories = ["Electronics", "Clothing", "Food", "Books", "Others"]
    values = [35, 25, 20, 10, 10]
    
    for i, (cat, val) in enumerate(zip(categories, values), 2):
        ws.cells[f"A{i}"].value = cat
        ws.cells[f"B{i}"].value = val
    
    # Create pie chart
    chart = ws.charts.add_pie(0, 4, 20, 12)
    chart.title = "Sales Distribution by Category"
    chart.category_data = "A2:A6"
    chart.show_legend = True
    chart.legend_position = "right"
    chart.vary_colors = True
    chart.first_slice_angle = 0
    
    # Add series
    chart.n_series.add("B2:B6", category_data="A2:A6", name="Sales")
    
    # Save
    output_path = examples_output_path("progcharts", "example_pie_chart.xlsx")
    wb.save(output_path)
    assert os.path.exists(output_path)
    print(f"Created: {output_path}")