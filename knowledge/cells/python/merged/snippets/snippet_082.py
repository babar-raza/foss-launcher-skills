def test_create_treemap_chart():
    """Create a treemap chart from scratch."""
    wb = Workbook()
    ws = wb.worksheets[0]
    
    # Add data
    ws.cells["A1"].value = "Category"
    ws.cells["B1"].value = "Subcategory"
    ws.cells["C1"].value = "Value"
    
    data = [
        ["Electronics", "Phones", 500],
        ["Electronics", "Laptops", 400],
        ["Electronics", "Tablets", 200],
        ["Clothing", "Shirts", 300],
        ["Clothing", "Pants", 250],
        ["Clothing", "Shoes", 200],
        ["Food", "Fruits", 150],
        ["Food", "Vegetables", 120],
        ["Food", "Dairy", 100]
    ]
    
    for i, (cat, sub, val) in enumerate(data, 2):
        ws.cells[f"A{i}"].value = cat
        ws.cells[f"B{i}"].value = sub
        ws.cells[f"C{i}"].value = val
    
    # Create treemap chart
    chart = ws.charts.add_treemap(0, 4, 20, 12)
    chart.title = "Sales by Category and Subcategory"
    chart.category_data = "A2:A10"
    chart.show_legend = True
    
    # Add series
    chart.n_series.add("C2:C10", category_data="A2:A10", name="Sales")
    
    # Save
    output_path = examples_output_path("progcharts", "example_treemap_chart.xlsx")
    wb.save(output_path)
    assert os.path.exists(output_path)
    print(f"Created: {output_path}")