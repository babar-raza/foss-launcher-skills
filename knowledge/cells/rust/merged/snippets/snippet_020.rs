let mut tables = sheet.get_list_objects();
let table_index = tables.add_a1("A1", "D5", true)?;
let mut table = tables.get(table_index as usize).expect("table should exist");
table.set_display_name("Products")?;
table.set_table_style_type(TableStyleType::TableStyleMedium2);
table.set_show_totals(true);

let mut columns = table.get_list_columns();
columns.get(3).expect("quantity column").set_totals_calculation(TotalsCalculation::Sum);
