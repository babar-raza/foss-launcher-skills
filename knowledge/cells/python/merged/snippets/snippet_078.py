def test_create_combo_chart():
    """Create a combo chart from scratch."""
    wb = Workbook()
    ws = wb.worksheets[0]
    
    # Add data
    ws.cells["A1"].value = "Month"
    ws.cells["B1"].value = "Sales"
    ws.cells["C1"].value = "Profit %"
    
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
    sales = [100, 150, 120, 180, 200, 170]
    profit_pct = [20, 25, 18, 22, 28, 24]
    
    for i, (month, sale, profit) in enumerate(zip(months, sales, profit_pct), 2):
        ws.cells[f"A{i}"].value = month
        ws.cells[f"B{i}"].value = sale
        ws.cells[f"C{i}"].value = profit
    
    # Create combo chart
    chart = ws.charts.add_combo(0, 4, 20, 12)
    chart.title = "Sales and Profit Margin"
    chart.category_data = "A2:A7"
    chart.show_legend = True
    
    # Add series with different chart types
    chart.n_series.add("B2:B7", category_data="A2:A7", name="Sales", chart_type=ChartType.BAR)
    chart.n_series.add("C2:C7", category_data="A2:A7", name="Profit %", chart_type=ChartType.LINE)
    
    # Configure sub-charts
    chart.sub_charts.append({
        'type': ChartType.BAR,
        'series': [0],
        'bar_direction': 'col',
        'grouping': 'clustered',
        'gap_width': 150,
        'ax_ids': [70000000, 70000001]
    })
    chart.sub_charts.append({
        'type': ChartType.LINE,
        'series': [1],
        'ax_ids': [70000000, 70000002]
    })
    
    # Add axes
    chart.add_axis(axis_type="cat", axis_id=70000000, position="b")
    chart.add_axis(axis_type="val", axis_id=70000001, position="l")
    chart.add_axis(axis_type="val", axis_id=70000002, position="r")
    
    # Save
    output_path = examples_output_path("progcharts", "example_combo_chart.xlsx")
    wb.save(output_path)
    assert os.path.exists(output_path)
    print(f"Created: {output_path}")