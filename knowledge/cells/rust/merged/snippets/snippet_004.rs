fn main() -> Result<(), Box<dyn Error>> {
    let output_path = common::output_path("conditional-formatting-sample.xlsx");

    let mut workbook = Workbook::new();
    {
        let mut worksheets = workbook.get_worksheets_mut();
        let sheet = worksheets.get(0)?;
        sheet.set_name("Conditional Formatting")?;
        let mut cells = sheet.get_cells_mut();

        for index in 0..10 {
            cells
                .get_by_index(index, 0)
                .put_value_i32((index + 1) as i32)?;
            cells
                .get_by_index(index, 1)
                .put_value_i32(((index + 1) * 10) as i32)?;
            cells
                .get_by_index(index, 2)
                .put_value_i32(((index + 1) * 10) as i32)?;
            cells
                .get_by_index(index, 3)
                .put_value_i32(((index + 1) * 10) as i32)?;
            cells
                .get_by_index(index, 4)
                .put_value_i32(((index + 1) * 10) as i32)?;
        }

        let mut collections = sheet.get_conditional_formattings();

        let between_collection_index = collections.add();
        let mut between_collection = collections
            .get(between_collection_index)
            .expect("collection should exist");
        between_collection.add_area(CellArea::create_cell_area_a1("A1", "A10")?)?;
        let between_rule_index = between_collection.add_condition_with_details(
            FormatConditionType::CellValue,
            OperatorType::Between,
            "3",
            "7",
        );
        let mut between_rule = between_collection
            .get(between_rule_index)
            .expect("rule should exist");
        between_rule.set_priority(1)?;
        between_rule.set_stop_if_true(true);
        let mut between_style = between_rule.get_style();
        between_style.pattern = FillPattern::Solid;
        between_style.fill_color = Some("FFFFC7CE".to_string());
        let between_font = between_style.get_font_mut();
        between_font.set_color("FF9C0006");
        between_font.set_is_bold(true);
        between_rule.set_style(between_style);

        let expression_collection_index = collections.add();
        let mut expression_collection = collections
            .get(expression_collection_index)
            .expect("collection should exist");
        expression_collection.add_area(CellArea::create_cell_area_a1("B1", "B10")?)?;
        let expression_rule_index = expression_collection.add_condition_with_details(
            FormatConditionType::Expression,
            OperatorType::None,
            "MOD(B1,20)=0",
            "",
        );
        let mut expression_rule = expression_collection
            .get(expression_rule_index)
            .expect("rule should exist");
        expression_rule.set_priority(2)?;
        let mut expression_style = expression_rule.get_style();
        let expression_font = expression_style.get_font_mut();
        expression_font.set_is_italic(true);
        expression_font.set_color("FF0000FF");
        expression_rule.set_style(expression_style);

        let color_scale_collection_index = collections.add();
        let mut color_scale_collection = collections
            .get(color_scale_collection_index)
            .expect("collection should exist");
        color_scale_collection.add_area(CellArea::create_cell_area_a1("C1", "C10")?)?;
        let color_scale_rule_index =
            color_scale_collection.add_condition(FormatConditionType::ColorScale);
        let mut color_scale_rule = color_scale_collection
            .get(color_scale_rule_index)
            .expect("rule should exist");
        color_scale_rule.set_color_scale_count(3)?;
        color_scale_rule.set_min_color("FFF8696B");
        color_scale_rule.set_mid_color("FFFFEB84");
        color_scale_rule.set_max_color("FF63BE7B");

        let data_bar_collection_index = collections.add();
        let mut data_bar_collection = collections
            .get(data_bar_collection_index)
            .expect("collection should exist");
        data_bar_collection.add_area(CellArea::create_cell_area_a1("D1", "D10")?)?;
        let data_bar_rule_index = data_bar_collection.add_condition(FormatConditionType::DataBar);
        let mut data_bar_rule = data_bar_collection
            .get(data_bar_rule_index)
            .expect("rule should exist");
        data_bar_rule.set_bar_color("FF638EC6");
        data_bar_rule.set_negative_bar_color("FFFF0000");
        data_bar_rule.set_show_border(true);
        data_bar_rule.set_direction("left-to-right");

        let icon_set_collection_index = collections.add();
        let mut icon_set_collection = collections
            .get(icon_set_collection_index)
            .expect("collection should exist");
        icon_set_collection.add_area(CellArea::create_cell_area_a1("E1", "E10")?)?;
        let icon_set_rule_inde