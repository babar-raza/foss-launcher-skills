fn main() -> Result<(), Box<dyn Error>> {
    let valid_path = common::output_path("loading-sample.xlsx");

    let mut workbook = Workbook::new();
    {
        let mut worksheets = workbook.get_worksheets_mut();
        let sheet = worksheets.get(0)?;
        let mut cells = sheet.get_cells_mut();

        cells.get("A1")?.put_value_string("Item")?;
        cells.get("B1")?.put_value_string("Quantity")?;
        cells.get("C1")?.put_value_string("Active")?;
        cells.get("A2")?.put_value_string("Apples")?;
        cells.get("B2")?.put_value_i32(12)?;
        cells.get("C2")?.put_value_bool(true)?;
        cells.get("A3")?.put_value_string("Oranges")?;
        cells.get("B3")?.put_value_i32(8)?;
        cells.get("C3")?.put_value_bool(false)?;
    }
    workbook.save(&valid_path)?;

    let options = LoadOptions {
        try_repair_package: true,
        try_repair_xml: true,
        ..LoadOptions::default()
    };

    let loaded = Workbook::load_xlsx_with_options(&valid_path, &options)?;
    let sheet = loaded.worksheet("Sheet1")?;
    let cells = sheet.get_cells();

    println!("Saved: {}", valid_path.display());
    println!(
        "Loaded workbook with {} worksheet(s) and {} diagnostic issue(s).",
        loaded.get_worksheets().count(),
        loaded.get_load_diagnostics().issues().len()
    );
    println!("First item: {}", cells.get("A2")?.display_string_value());
    println!(
        "Second quantity: {}",
        cells.get("B3")?.display_string_value()
    );

    Ok(())
}