fn main() -> Result<(), Box<dyn Error>> {
    let output_path = common::output_path("worksheet-settings-sample.xlsx");

    let mut workbook = Workbook::new();
    {
        let mut worksheets = workbook.get_worksheets_mut();
        {
            let layout = worksheets.get(0)?;
            layout.set_name("Layout")?;
            layout.set_visibility_type(VisibilityType::Hidden);
            layout.set_tab_color(Color::from_argb(255, 34, 68, 102));
            layout.set_show_gridlines(false);
            layout.set_show_row_column_headers(false);
            layout.set_show_zeros(false);
            layout.set_right_to_left(true);
            layout.set_zoom(85)?;
            layout.protect();

            {
                let protection = layout.get_protection_mut();
                protection.set_objects(true);
                protection.set_scenarios(true);
                protection.set_format_cells(true);
                protection.set_insert_rows(true);
                protection.set_auto_filter(true);
                protection.set_select_locked_cells(true);
                protection.set_select_unlocked_cells(true);
            }

            let mut cells = layout.get_cells_mut();
            cells.get("A1")?.put_value_string("Merged")?;
            cells.get("C4")?.put_value_i32(99)?;
            cells.get_rows().get(1).set_height(22.5)?;
            cells.get_rows().get(3).set_is_hidden(true)?;
            cells.get_columns().get(0).set_width(18.25)?;
            cells.get_columns().get(2).set_is_hidden(true)?;
            let mut cells = layout.get_cells_mut();
            cells.merge(0, 0, 2, 2)?;
        }

        let visible_index = worksheets.add("Visible")?;
        {
            let visible_sheet = worksheets.get(visible_index)?;
            visible_sheet
                .get_cells_mut()
                .get("A1")?
                .put_value_string("Visible")?;
        }
        worksheets.set_active_sheet_name("Visible")?;
    }

    workbook.save(&output_path)?;

    let loaded = Workbook::load_xlsx(&output_path)?;
    let sheets = loaded.get_worksheets();
    let layout = sheets.get_by_name("Layout")?;

    println!("Saved: {}", output_path.display());
    println!("Active sheet: {}", sheets.active_sheet_name());
    println!("Layout visibility: {:?}", layout.get_visibility_type());
    println!(
        "Merged value: {}",
        layout.get_cells().get("A1")?.display_string_value()
    );
    println!(
        "Row 2 height: {}",
        layout.get_rows().get(1).get_height().unwrap_or_default()
    );
    println!(
        "Column A width: {}",
        layout.get_columns().get(0).get_width().unwrap_or_default()
    );
    println!(
        "Merged regions: {}",
        layout.get_cells().get_merged_cells().len()
    );

    Ok(())
}