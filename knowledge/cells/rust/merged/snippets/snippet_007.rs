fn main() -> Result<(), Box<dyn Error>> {
    let output_path = common::output_path("listobjects-sample.xlsx");

    let mut workbook = Workbook::new();
    {
        let mut worksheets = workbook.get_worksheets_mut();
        let sheet = worksheets.get(0)?;
        sheet.set_name("Data")?;
        let mut cells = sheet.get_cells_mut();

        for (address, value) in [
            ("A1", "Product"),
            ("B1", "Category"),
            ("C1", "Price"),
            ("D1", "Quantity"),
            ("A2", "Laptop"),
            ("B2", "Electronics"),
            ("A3", "Mouse"),
            ("B3", "Electronics"),
            ("A4", "Desk Chair"),
            ("B4", "Furniture"),
            ("A5", "Monitor"),
            ("B5", "Electronics"),
        ] {
            cells.get(address)?.put_value_string(value)?;
        }

        cells.get("C2")?.put_value_f64(999.99)?;
        cells.get("D2")?.put_value_i32(50)?;
        cells.get("C3")?.put_value_f64(29.99)?;
        cells.get("D3")?.put_value_i32(200)?;
        cells.get("C4")?.put_value_f64(149.99)?;
        cells.get("D4")?.put_value_i32(75)?;
        cells.get("C5")?.put_value_f64(349.99)?;
        cells.get("D5")?.put_value_i32(100)?;
        // Note: the totals row (row 6) is intentionally left empty here. It is
        // filled in automatically from the column totals declarations below, so
        // the library emits the structured SUBTOTAL formula that Excel requires.

        let mut tables = sheet.get_list_objects();
        let table_index = tables.add_a1("A1", "D5", true)?;
        let mut table = tables
            .get(table_index as usize)
            .expect("table should exist");
        table.set_display_name("Products")?;
        table.set_comment("Product inventory table");
        table.set_table_style_type(TableStyleType::TableStyleMedium2);
        table.set_show_table_style_first_column(true);
        table.set_show_table_style_last_column(true);
        table.set_show_table_style_row_stripes(true);
        table.set_show_totals(true);

        // Describe the totals row so Excel can reconcile it with the cells above:
        // a "Total" label under the first column and a SUM over the Quantity column.
        {
            let mut columns = table.get_list_columns();
            columns
                .get(0)
                .expect("first column should exist")
                .set_totals_row_label("Total");
            columns
                .get(3)
                .expect("quantity column should exist")
                .set_totals_calculation(TotalsCalculation::Sum);
        }
    }

    workbook.save(&output_path)?;

    let mut loaded = Workbook::load_xlsx(&output_path)?;
    let mut sheets = loaded.get_worksheets_mut();
    let sheet = sheets.get_by_name("Data")?;
    let mut tables = sheet.get_list_objects();
    let table_count = tables.count();
    let (
        table_name,
        table_comment,
        table_style,
        show_headers,
        show_totals,
        column_count,
        first_column_name,
    ) = {
        let mut table = tables.get_by_name("Products").expect("table should exist");
        let table_name = table.get_display_name().to_string();
        let table_comment = table.get_comment().to_string();
        let table_style = table.get_table_style_type();
        let show_headers = table.get_show_header_row();
        let show_totals = table.get_show_totals();
        let mut columns = table.get_list_columns();
        let column_count = columns.count();
        let first_column_name = columns
            .get(0)
            .expect("column should exist")
            .get_name()
            .to_string();
        (
            table_name,
            table_comment,
            table_style,
            show_headers,
            show_totals,
            column_count,
            first_column_name,
        )
    };

    println!("Saved: {}", output_path.display());
    println!("Table count: {}", table_count);
    println!("Table name: {}", table_name);
    println!("Table comment: {}", table_comment);
    println!("Table style: {:?}", table_style);
    println!("Show headers: {}", show_headers);
    println!("Show totals: {}", show_totals);
    println!("Column count: {}", column_count);
    println!("First column: {}", first_column_name);

    Ok(())
}