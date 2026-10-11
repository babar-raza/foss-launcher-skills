fn main() -> Result<(), Box<dyn Error>> {
    let output_path = common::output_path("cell-data-roundtrip.xlsx");
    let timestamp = Utc
        .with_ymd_and_hms(2024, 5, 6, 7, 8, 9)
        .single()
        .expect("timestamp should be valid");

    let mut workbook = Workbook::new();
    {
        let mut worksheets = workbook.get_worksheets_mut();
        let sheet = worksheets.get(0)?;
        let mut cells = sheet.get_cells_mut();

        cells.get("A1")?.put_value_string("Hello")?;
        cells.get("B1")?.put_value_i32(123)?;
        cells.get("C1")?.put_value_bool(true)?;
        cells.get("D1")?.put_value_decimal(12.5)?;
        cells.get("E1")?.put_value_date_time(timestamp)?;
        cells.get("F1")?.put_value_i32(10)?;
        cells
            .get("G1")?
            .put_formula_with_cached_value("=F1*2", CellValue::Number(20.0))?;
    }
    workbook.save(&output_path)?;

    let loaded = Workbook::load_xlsx(&output_path)?;
    let sheet = loaded.worksheet("Sheet1")?;
    let cells = sheet.get_cells();

    println!("Saved: {}", output_path.display());
    println!("{}", cells.get("A1")?.display_string_value());
    println!(
        "{:?}:{}",
        cells.get("B1")?.value_type(),
        cells.get("B1")?.display_string_value()
    );
    println!(
        "{:?}:{}",
        cells.get("C1")?.value_type(),
        cells.get("C1")?.display_string_value()
    );
    println!(
        "{:?}:{}",
        cells.get("D1")?.value_type(),
        cells.get("D1")?.display_string_value()
    );
    println!(
        "{:?}:{}",
        cells.get("E1")?.value_type(),
        cells.get("E1")?.display_string_value()
    );
    println!(
        "G1 cached value -> {}",
        cells.get("G1")?.display_string_value()
    );

    Ok(())
}