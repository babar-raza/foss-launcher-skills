fn main() -> Result<(), Box<dyn Error>> {
    let mut workbook = Workbook::new();
    {
        let mut worksheets = workbook.get_worksheets_mut();
        let sheet = worksheets.get(0)?;
        sheet.set_name("Style Gallery")?;

        let mut cells = sheet.get_cells_mut();
        configure_layout(&mut cells)?;
        write_title(&mut cells)?;
        write_font_section(&mut cells)?;
        write_fill_section(&mut cells)?;
        write_border_section(&mut cells)?;
        write_alignment_section(&mut cells)?;
        write_number_format_section(&mut cells)?;
        write_misc_section(&mut cells)?;
    }

    let output_path = common::output_path("styles-gallery-sample.xlsx");
    workbook.save(&output_path)?;
    println!("Saved: {}", output_path.display());

    let sheet = workbook.worksheet("Style Gallery")?;
    let cells = sheet.get_cells();
    print_summary(&cells)?;

    Ok(())
}