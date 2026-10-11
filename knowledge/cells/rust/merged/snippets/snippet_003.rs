fn main() -> Result<(), Box<dyn Error>> {
    let output_path = common::output_path("comments-sample.xlsx");

    let mut workbook = Workbook::new();
    {
        let mut worksheets = workbook.get_worksheets_mut();
        let sheet = worksheets.get(0)?;
        sheet.set_name("Comments")?;
        let mut cells = sheet.get_cells_mut();
        cells.get("A1")?.put_value_string("Task")?;
        cells.get("B1")?.put_value_string("Status")?;
        cells.get("A2")?.put_value_string("Design UI")?;
        cells.get("B2")?.put_value_string("In Progress")?;
        cells.get("A3")?.put_value_string("Implement API")?;
        cells.get("B3")?.put_value_string("Pending")?;
        cells.get("A4")?.put_value_string("Write Tests")?;
        cells.get("B4")?.put_value_string("Completed")?;

        let mut comments = sheet.get_comments();
        let comment2_index = comments.add(1, 0)?;
        let mut comment2 = comments.get(comment2_index).expect("comment should exist");
        comment2.set_author("John");
        comment2.set_note("Need to finalize the color scheme by Friday");
        comment2.set_is_visible(false);
        comment2.set_width(200.0)?;
        comment2.set_height(100.0)?;

        let comment3_index = comments.add_a1("A3")?;
        let mut comment3 = comments.get(comment3_index).expect("comment should exist");
        comment3.set_author("Sarah");
        comment3.set_note("Waiting for database schema approval");
        comment3.set_is_visible(true);
        comment3.set_width(180.0)?;
        comment3.set_height(90.0)?;

        let comment4_index = comments.add_a1("B4")?;
        let mut comment4 = comments.get(comment4_index).expect("comment should exist");
        comment4.set_author("Mike");
        comment4.set_note("All unit tests passing. Ready for review.");
        comment4.set_is_visible(false);
    }

    workbook.save(&output_path)?;

    let mut loaded = Workbook::load_xlsx(&output_path)?;
    let mut sheets = loaded.get_worksheets_mut();
    let sheet = sheets.get_by_name("Comments")?;
    let mut comments = sheet.get_comments();
    let a2 = {
        let comment = comments.get_by_cell_name("A2")?.expect("comment");
        (
            comment.get_author().to_string(),
            comment.get_note().to_string(),
        )
    };
    let a3_visible = {
        let comment = comments.get_by_cell_name("A3")?.expect("comment");
        comment.get_is_visible()
    };
    let b4 = {
        let comment = comments.get_by_cell_name("B4")?.expect("comment");
        comment.get_note().to_string()
    };

    println!("Saved: {}", output_path.display());
    println!("Comment count: {}", comments.count());
    println!("A2 comment by {}: {}", a2.0, a2.1);
    println!("A3 comment visible: {}", a3_visible);
    println!("B4 comment: {}", b4);

    Ok(())
}