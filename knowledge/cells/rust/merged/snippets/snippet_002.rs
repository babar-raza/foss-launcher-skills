fn main() -> Result<(), Box<dyn Error>> {
    let output_path = common::output_path("charts-sample.xlsx");

    let mut workbook = Workbook::new();
    {
        let mut worksheets = workbook.get_worksheets_mut();
        let sheet = worksheets.get(0)?;
        sheet.set_name("Charts")?;
        {
            let mut cells = sheet.get_cells_mut();
            cells.get("A1")?.put_value_string("Month")?;
            cells.get("B1")?.put_value_string("Sales")?;
            cells.get("C1")?.put_value_string("Profit")?;

            for month in 1..=12_u32 {
                cells
                    .get_by_index(month, 0)
                    .put_value_string(format!("Month {month}"))?;
                cells
                    .get_by_index(month, 1)
                    .put_value_i32((month as i32 * 1000) + (month as i32 * 50))?;
                cells
                    .get_by_index(month, 2)
                    .put_value_i32((month as i32 * 300) + (month as i32 * 20))?;
            }
        }

        let mut charts = sheet.get_charts();
        charts.add(
            ChartType::Column,
            "Charts!$B$1:$B$13".to_string(),
            0,
            4,
            18,
            8,
        )?;
        charts.add(
            ChartType::Line,
            "Charts!$C$1:$C$13".to_string(),
            0,
            9,
            18,
            13,
        )?;
    }

    workbook.save(&output_path)?;

    let mut loaded = Workbook::load_xlsx(&output_path)?;
    let mut sheets = loaded.get_worksheets_mut();
    let sheet = sheets.get_by_name("Charts")?;
    let mut charts = sheet.get_charts();
    let chart_count = charts.count();
    let first = {
        let chart = charts.get(0).expect("chart");
        (
            chart.get_name().to_string(),
            chart.get_chart_type(),
            chart.get_upper_left_row(),
            chart.get_upper_left_column(),
            chart.get_lower_right_row(),
            chart.get_lower_right_column(),
        )
    };
    let second = {
        let chart = charts.get(1).expect("chart");
        (chart.get_name().to_string(), chart.get_chart_type())
    };

    println!("Saved: {}", output_path.display());
    println!("Chart count: {}", chart_count);
    println!("First chart: {} (Type: {:?})", first.0, first.1);
    println!("Second chart: {} (Type: {:?})", second.0, second.1);
    println!(
        "First chart anchor: R{}C{} to R{}C{}",
        first.2, first.3, first.4, first.5
    );

    Ok(())
}