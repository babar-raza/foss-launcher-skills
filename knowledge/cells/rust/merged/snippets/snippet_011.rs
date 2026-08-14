fn main() -> Result<(), Box<dyn Error>> {
    let output_path = common::output_path("shapes-sample.xlsx");

    let mut workbook = Workbook::new();
    {
        let mut worksheets = workbook.get_worksheets_mut();
        let sheet = worksheets.get(0)?;
        sheet.set_name("Shapes")?;
        let mut cells = sheet.get_cells_mut();
        cells.get("A1")?.put_value_string("Shape")?;
        cells.get("B1")?.put_value_string("Description")?;

        let shape_specs = [
            (0, 2, 2, 3, AutoShapeType::Rectangle, "Rectangle Box"),
            (
                0,
                4,
                2,
                5,
                AutoShapeType::RoundedRectangle,
                "Rounded Rectangle",
            ),
            (0, 6, 2, 7, AutoShapeType::Ellipse, "Oval Shape"),
            (3, 2, 5, 3, AutoShapeType::Triangle, "Triangle"),
            (3, 4, 5, 5, AutoShapeType::RightTriangle, "Right Triangle"),
            (3, 6, 5, 7, AutoShapeType::Diamond, "Diamond"),
            (6, 2, 8, 3, AutoShapeType::Pentagon, "Pentagon"),
            (6, 4, 8, 5, AutoShapeType::Hexagon, "Hexagon"),
            (6, 6, 8, 7, AutoShapeType::Octagon, "Octagon"),
            (9, 2, 11, 3, AutoShapeType::Star5Point, "5-Point Star"),
            (9, 4, 11, 5, AutoShapeType::Star8Point, "8-Point Star"),
            (9, 6, 11, 7, AutoShapeType::Star12Point, "12-Point Star"),
            (12, 2, 14, 3, AutoShapeType::RightArrow, "Right Arrow"),
            (12, 4, 14, 5, AutoShapeType::LeftArrow, "Left Arrow"),
            (12, 6, 14, 7, AutoShapeType::UpDownArrow, "Up-Down Arrow"),
            (15, 2, 17, 3, AutoShapeType::Heart, "Heart"),
            (15, 4, 17, 5, AutoShapeType::Lightning, "Lightning Bolt"),
            (15, 6, 17, 7, AutoShapeType::Cloud, "Cloud"),
            (18, 2, 20, 3, AutoShapeType::Sun, "Sun"),
            (18, 4, 20, 5, AutoShapeType::Moon, "Moon"),
            (18, 6, 20, 7, AutoShapeType::Plus, "Plus Sign"),
            (21, 2, 23, 3, AutoShapeType::Cube, "Cube"),
            (21, 4, 23, 5, AutoShapeType::Cylinder, "Cylinder"),
            (21, 6, 23, 7, AutoShapeType::MathPlus, "Math Plus"),
        ];

        let mut shapes = sheet.get_shapes();
        for (ul_row, ul_col, lr_row, lr_col, shape_type, name) in shape_specs {
            let index = shapes.add(ul_row, ul_col, lr_row, lr_col, shape_type)?;
            let mut shape = shapes.get(index).expect("shape should exist");
            shape.set_name(name);
        }
    }

    workbook.save(&output_path)?;

    let mut loaded = Workbook::load_xlsx(&output_path)?;
    let mut sheets = loaded.get_worksheets_mut();
    let sheet = sheets.get_by_name("Shapes")?;
    let mut shapes = sheet.get_shapes();

    println!("Saved: {}", output_path.display());
    println!("Shape count: {}", shapes.count());
    for index in [0_usize, 1, 2, 9, 12, 15, 21] {
        let shape = shapes.get(index).expect("shape should exist");
        println!("{} ({:?})", shape.get_name(), shape.get_auto_shape_type());
    }

    Ok(())
}