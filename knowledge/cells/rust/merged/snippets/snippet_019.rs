let mut validations = sheet.get_validations();
let list_index = validations.add(CellArea::create_cell_area_a1("A1", "A3")?)?;
let mut list_validation = validations.get(list_index).expect("validation should exist");
list_validation.set_type(ValidationType::List);
list_validation.set_formula1("\"Open,Closed\"");
list_validation.set_in_cell_drop_down(true);
list_validation.set_show_error(true);
list_validation.set_error_title("Invalid");
list_validation.set_error_message("Choose from the list");
