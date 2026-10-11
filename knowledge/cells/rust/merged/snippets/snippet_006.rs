fn main() -> Result<(), Box<dyn Error>> {
    let output_path = common::output_path("hyperlinks-and-names-sample.xlsx");

    let mut workbook = Workbook::new();
    let scoped_sheet_index;
    {
        let mut worksheets = workbook.get_worksheets_mut();
        scoped_sheet_index = worksheets.add("Scoped Sheet")?;
        {
            let scoped_sheet = worksheets.get(scoped_sheet_index)?;
            scoped_sheet.get_cells_mut().get("B2")?.put_value_i32(5)?;
        }
        {
            let links_sheet = worksheets.get(0)?;
            links_sheet.set_name("Links")?;
            links_sheet
                .get_cells_mut()
                .get("A1")?
                .put_value_string("Docs")?;
            links_sheet
                .get_cells_mut()
                .get("B2")?
                .put_value_string("Jump")?;
            links_sheet
                .get_cells_mut()
                .get("C4")?
                .put_value_string("Mail")?;

            {
                let mut hyperlinks = links_sheet.get_hyperlinks();
                let external_index = hyperlinks.add("A1", 1, 1, "https://example.com/docs?q=1")?;
                let mut external_link = hyperlinks
                    .get(external_index)
                    .expect("hyperlink should exist");
                external_link.set_text_to_display("Docs");
                external_link.set_screen_tip("External docs");

                let internal_index = hyperlinks.add("B2", 1, 1, "'Scoped Sheet'!B2")?;
                let mut internal_link = hyperlinks
                    .get(internal_index)
                    .expect("hyperlink should exist");
                internal_link.set_text_to_display("Jump");
                internal_link.set_screen_tip("Jump to scoped sheet");

                let mail_index = hyperlinks.add("C4", 2, 2, "mailto:test@example.com")?;
                let mut mail_link = hyperlinks.get(mail_index).expect("hyperlink should exist");
                mail_link.set_text_to_display("Mail");
                mail_link.set_screen_tip("Send mail");
            }

            // Apply the standard hyperlink text style (blue, underlined) to linked cells.
            let mut cells = links_sheet.get_cells_mut();
            for address in ["A1", "B2", "C4"] {
                let mut cell = cells.get(address)?;
                let mut style = cell.get_style();
                let font = style.get_font_mut();
                font.set_color(HYPERLINK_COLOR);
                font.set_underline(FontUnderlineType::Single);
                cell.set_style(style)?;
            }
        }
    }

    {
        let mut defined_names = workbook.get_defined_names();
        let global_index = defined_names.add("GlobalRange", "='Links'!$A$1:$D$5")?;
        let mut global_name = defined_names
            .get(global_index)
            .expect("defined name should exist");
        global_name.set_hidden(true);
        global_name.set_comment("Primary sample range");

        let local_index = defined_names.add_with_scope(
            "ScopedCell",
            "'Scoped Sheet'!$B$2",
            Some(scoped_sheet_index),
        )?;
        let mut local_name = defined_names
            .get(local_index)
            .expect("defined name should exist");
        local_name.set_comment("Sheet-scoped name");
    }

    workbook.save(&output_path)?;

    let mut loaded = Workbook::load_xlsx(&output_path)?;
    let (hyperlink_count, first, second) = {
        let mut sheets = loaded.get_worksheets_mut();
        let links_sheet = sheets.get_by_name("Links")?;
        let mut hyperlinks = links_sheet.get_hyperlinks();
        let count = hyperlinks.count();
        let first = {
            let hyperlink = hyperlinks.get(0).expect("hyperlink");
            (hyperlink.get_address().to_string(), hyperlink.get_area())
        };
        let second = {
            let hyperlink = hyperlinks.get(1).expect("hyperlink");
            (hyperlink.get_address().to_string(), hyperlink.get_area())
        };
        (count, first, second)
    };
    let mut defined_names = loaded.get_defined_names();

    println!("Saved: {}", output_path.display());
    println!("Hyperlinks: {}", hyperlink_count);
    println!("First hyperlink: {} / {}", first.0, first.1);
    println!("Second hyperlink: {} / {}", second.0, second.1);
    println!("Defined names: {}", defined_names.count());
    println!(
        "Global name formula: {}",
        defined_names.get(0).expect("name").get_formula()
    );
    println!(
        "Local name scope: {}",
        defined_names
            .get(1)
            .expect("name")
            .get_local_sheet_index()
            .map(|value| value as i32)
            .unwrap_or(-1)
    );

    Ok(())
}