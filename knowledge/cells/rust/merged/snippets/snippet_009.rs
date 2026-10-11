fn main() -> Result<(), Box<dyn Error>> {
    let output_path = common::output_path("page-setup-sample.xlsx");

    let mut workbook = Workbook::new();
    {
        let mut worksheets = workbook.get_worksheets_mut();
        let sheet = worksheets.get(0)?;
        sheet.set_name("Print Sheet")?;
        let mut cells = sheet.get_cells_mut();
        cells.get("A1")?.put_value_string("Title")?;
        cells.get("C10")?.put_value_i32(42)?;

        let page_setup = sheet.get_page_setup_mut();
        page_setup.set_left_margin_inch(0.25)?;
        page_setup.set_right_margin_inch(0.4)?;
        page_setup.set_top_margin_inch(0.5)?;
        page_setup.set_bottom_margin_inch(0.6)?;
        page_setup.set_header_margin_inch(0.2)?;
        page_setup.set_footer_margin_inch(0.22)?;
        page_setup.set_orientation(PageOrientationType::Landscape);
        page_setup.set_paper_size(PaperSizeType::PaperA4);
        page_setup.set_first_page_number(Some(3))?;
        page_setup.set_scale(Some(95))?;
        page_setup.set_fit_to_pages_wide(Some(1))?;
        page_setup.set_fit_to_pages_tall(Some(2))?;
        page_setup.set_print_area("$A$1:$C$10");
        page_setup.set_print_title_rows("$1:$2");
        page_setup.set_print_title_columns("$A:$B");
        page_setup.set_left_header("Left Header");
        page_setup.set_center_header("Center Header");
        page_setup.set_right_header("Right Header");
        page_setup.set_left_footer("Left Footer");
        page_setup.set_center_footer("Center Footer");
        page_setup.set_right_footer("Right Footer");
        page_setup.set_print_gridlines(true);
        page_setup.set_print_headings(true);
        page_setup.set_center_horizontally(true);
        page_setup.set_center_vertically(true);
        page_setup.add_horizontal_page_break(4)?;
        page_setup.add_horizontal_page_break(7)?;
        page_setup.add_vertical_page_break(2)?;
    }

    workbook.save(&output_path)?;

    let loaded = Workbook::load_xlsx(&output_path)?;
    let page_setup = loaded.worksheet_at(0)?.get_page_setup();

    println!("Saved: {}", output_path.display());
    println!("Orientation: {:?}", page_setup.get_orientation());
    println!("Paper size: {:?}", page_setup.get_paper_size());
    println!("Print area: {}", page_setup.get_print_area());
    println!(
        "Horizontal breaks: {:?}",
        page_setup.get_horizontal_page_breaks()
    );
    println!(
        "Vertical breaks: {:?}",
        page_setup.get_vertical_page_breaks()
    );

    Ok(())
}