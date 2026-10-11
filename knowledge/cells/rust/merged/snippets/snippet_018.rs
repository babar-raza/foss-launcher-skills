let mut collections = sheet.get_conditional_formattings();

let between_index = collections.add();
let mut between = collections.get(between_index).expect("collection should exist");
between.add_area(CellArea::create_cell_area_a1("A1", "A10")?)?;
let rule_index = between.add_condition_with_details(
    FormatConditionType::CellValue,
    OperatorType::Between,
    "3",
    "7",
);
let mut rule = between.get(rule_index).expect("rule should exist");
rule.set_priority(1)?;
let mut style = rule.get_style();
style.pattern = FillPattern::Solid;
style.fill_color = Some("FFFFC7CE".to_string());
rule.set_style(style);
