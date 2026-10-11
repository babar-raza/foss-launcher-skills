def test_create_sunburst_chart():
    """Create a sunburst chart from scratch."""
    wb = Workbook()
    ws = wb.worksheets[0]
    
    # Add data - hierarchical structure with 3 levels
    ws.cells["A1"].value = "Category"
    ws.cells["B1"].value = "Subcategory"
    ws.cells["C1"].value = "Item"
    ws.cells["D1"].value = "Value"
    
    data = [
        ["Electronics", "Phones", "iPhone", 200],
        ["Electronics", "Phones", "Samsung", 150],
        ["Electronics", "Laptops", "MacBook", 180],
        ["Electronics", "Laptops", "Dell", 120],
        ["Clothing", "Shirts", "T-Shirt", 100],
        ["Clothing", "Shirts", "Polo", 80],
        ["Clothing", "Pants", "Jeans", 90],
        ["Clothing", "Pants", "Chinos", 70],
        ["Food", "Fruits", "Apples", 60],
        ["Food", "Fruits", "Oranges", 50],
        ["Food", "Vegetables", "Carrots", 40],
        ["Food", "Vegetables", "Broccoli", 35]
    ]
    
    for i, (cat, sub, item, val) in enumerate(data, 2):
        ws.cells[f"A{i}"].value = cat
        ws.cells[f"B{i}"].value = sub
        ws.cells[f"C{i}"].value = item
        ws.cells[f"D{i}"].value = val
    
    # Create sunburst chart
    chart = ws.charts.add_sunburst(0, 4, 20, 12)
    chart.title = "Sales Hierarchy - Sunburst"
    chart.show_legend = True
    
    # Add series
    chart.n_series.add("D2:D13", category_data="A2:A13", name="Sales")
    
    # Save
    output_path = examples_output_path("progcharts", "example_sunburst_chart.xlsx")
    wb.save(output_path)
    assert os.path.exists(output_path)
    print(f"Created: {output_path}")