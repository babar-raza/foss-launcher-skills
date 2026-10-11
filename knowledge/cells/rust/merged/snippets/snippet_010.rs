fn main() -> Result<(), Box<dyn Error>> {
    let output_path = common::output_path("pictures-sample.xlsx");
    let sample_image_data = common::sample_png_bytes();

    let mut workbook = Workbook::new();
    {
        let mut worksheets = workbook.get_worksheets_mut();
        let sheet = worksheets.get(0)?;
        sheet.set_name("Pictures")?;
        let mut cells = sheet.get_cells_mut();

        for (address, value) in [
            ("A1", "Product"),
            ("B1", "Description"),
            ("A2", "Item 1"),
            ("B2", "Sample product with logo"),
            ("A4", "Item 2"),
            ("B4", "Another product"),
        ] {
            cells.get(address)?.put_value_string(value)?;
        }

        let mut pictures = sheet.get_pictures();
        let picture1_index = pictures.add(1, 4, 3, 6, sample_image_data.clone())?;
        let mut picture1 = pictures.get(picture1_index).expect("picture should exist");
        picture1.set_name("Product Logo 1");

        let picture2_index = pictures.add(3, 2, 5, 3, sample_image_data)?;
        let mut picture2 = pictures.get(picture2_index).expect("picture should exist");
        picture2.set_name("Product Logo 2");
        picture2.set_lower_right_column(5)?;
        picture2.set_upper_left_column(4)?;
    }

    workbook.save(&output_path)?;

    let mut loaded = Workbook::load_xlsx(&output_path)?;
    let mut sheets = loaded.get_worksheets_mut();
    let sheet = sheets.get_by_name("Pictures")?;
    let mut pictures = sheet.get_pictures();
    let picture_count = pictures.count();
    let first = {
        let picture = pictures.get(0).expect("picture");
        (
            picture.get_name().to_string(),
            picture.get_image_type(),
            picture.get_upper_left_row(),
            picture.get_upper_left_column(),
            picture.get_lower_right_row(),
            picture.get_lower_right_column(),
        )
    };
    let second = {
        let picture = pictures.get(1).expect("picture");
        (picture.get_name().to_string(), picture.get_image_type())
    };

    println!("Saved: {}", output_path.display());
    println!("Picture count: {}", picture_count);
    println!("First picture: {} (Type: {:?})", first.0, first.1);
    println!(
        "First picture anchor: R{}C{} to R{}C{}",
        first.2, first.3, first.4, first.5
    );
    println!("Second picture: {} (Type: {:?})", second.0, second.1);

    Ok(())
}