fn main() -> Result<(), Box<dyn Error>> {
    let output_path = common::output_path("validations-sample.xlsx");

    let mut workbook = Workbook::new();
    {
        let mut worksheets = workbook.get_worksheets_mut();
        let sheet = worksheets.get(0)?;
        sheet.set_name("Validation Sheet")?;
        let mut cells = sheet.get_cells_mut();
        cells.get("A1")?.put_value_string("Open")?;
        cells.get("B2")?.put_value_i32(5)?;
        cells.get("C3")?.put_value_i32(7)?;
        cells.get("E2")?.put_value_i32(8)?;
        cells.get("G1")?.put_value_string("ABCDE")?;

        let mut validations = sheet.get_validations();
        let list_index = validations.add(CellArea::create_cell_area_a1("A1", "A3")?)?;
        let mut list_validation = validations
            .get(list_index)
            .expect("validation should exist");
        list_validation.set_type(ValidationType::List);
        list_validation.set_formula1("\"Open,Closed\"");
        list_validation.set_ignore_blank(true);
        list_validation.set_in_cell_drop_down(true);
        list_validation.set_show_input(true);
        list_validation.set_input_title("Status");
        list_validation.set_input_message("Pick a status");
        list_validation.set_show_error(true);
        list_validation.set_error_title("Invalid");
        list_validation.set_error_message("Choose from the list");

        let decimal_index = validations.add(CellArea::create_cell_area_a1("B2", "C3")?)?;
        let mut decimal_validation = validations
            .get(decimal_index)
            .expect("validation should exist");
        decimal_validation.set_type(ValidationType::Decimal);
        decimal_validation.set_operator(OperatorType::Between);
        decimal_validation.set_formula1("1.5");
        decimal_validation.set_formula2("9.5");
        decimal_validation.set_error_title("Range");
        decimal_validation.set_error_message("Enter 1.5-9.5");
        decimal_validation.set_show_error(true);
        decimal_validation.add_area(CellArea::create_cell_area_a1("E2", "E3")?)?;

        let custom_index = validations.add(CellArea::create_cell_area_a1("G1", "G1")?)?;
        let mut custom_validation = validations
            .get(custom_index)
            .expect("validation should exist");
        custom_validation.set_type(ValidationType::Custom);
        custom_validation.set_alert_style(ValidationAlertType::Warning);
        custom_validation.set_formula1("LEN(G1)<=5");
        custom_validation.set_show_input(true);
        custom_validation.set_input_title("Code");
        custom_validation.set_input_message("Up to 5 chars");
    }

    workbook.save(&output_path)?;

    let mut loaded = Workbook::load_xlsx(&output_path)?;
    let mut sheets = loaded.get_worksheets_mut();
    let sheet = sheets.get_by_name("Validation Sheet")?;
    let mut validations = sheet.get_validations();
    let validation_count = validations.count();
    let (a1_type, a1_formula1) = {
        let a1 = validations
            .get_validation_in_cell(0, 0)?
            .expect("A1 validation should exist");
        (a1.get_type(), a1.get_formula1().to_string())
    };
    let (c2_type, c2_formula1, c2_formula2) = {
        let c2 = validations
            .get_validation_in_cell(1, 2)?
            .expect("C2 validation should exist");
        (
            c2.get_type(),
            c2.get_formula1().to_string(),
            c2.get_formula2().to_string(),
        )
    };
    let g1_type = {
        let g1 = validations
            .get_validation_in_cell(0, 6)?
            .expect("G1 validation should exist");
        g1.get_type()
    };

    println!("Saved: {}", output_path.display());
    println!("Validation count: {}", validation_count);
    println!("A1 validation: {:?} / {}", a1_type, a1_formula1);
    println!(
        "C2 validation: {:?} / {} to {}",
        c2_type, c2_formula1, c2_formula2
    );
    println!("G1 validation: {:?}", g1_type);

    Ok(())
}