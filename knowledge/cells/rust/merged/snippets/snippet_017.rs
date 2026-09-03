let mut charts = sheet.get_charts();
charts.add(
    ChartType::Column,
    "Charts!$B$1:$B$13".to_string(),
    0, 4, 18, 8,
)?;
charts.add(
    ChartType::Line,
    "Charts!$C$1:$C$13".to_string(),
    0, 9, 18, 13,
)?;

let chart_count = charts.count();
let first = charts.get(0).expect("chart");
println!("Chart count: {}", chart_count);
println!("First chart type: {:?}", first.get_chart_type());
