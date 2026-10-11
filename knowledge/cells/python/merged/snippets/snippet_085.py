def test_create_funnel_chart():
    """Create a funnel chart from scratch."""
    wb = Workbook()
    ws = wb.worksheets[0]
    
    # Add data - sales funnel stages
    ws.cells["A1"].value = "Stage"
    ws.cells["B1"].value = "Count"
    
    stages = ["Website Visitors", "Product Page Views", "Add to Cart", "Checkout", "Purchase"]
    counts = [10000, 5000, 2000, 1000, 500]
    
    for i, (stage, count) in enumerate(zip(stages, counts), 2):
        ws.cells[f"A{i}"].value = stage
        ws.cells[f"B{i}"].value = count
    
    # Create funnel chart
    chart = ws.charts.add_funnel(0, 4, 20, 12)
    chart.title = "Sales Funnel"
    chart.show_legend = True
    
    # Add series
    chart.n_series.add("B2:B6", category_data="A2:A6", name="Funnel")
    
    # Save
    output_path = examples_output_path("progcharts", "example_funnel_chart.xlsx")
    wb.save(output_path)
    assert os.path.exists(output_path)
    print(f"Created: {output_path}")