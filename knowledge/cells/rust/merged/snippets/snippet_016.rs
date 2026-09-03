let options = LoadOptions {
    try_repair_package: true,
    try_repair_xml: true,
    ..LoadOptions::default()
};

let loaded = Workbook::load_xlsx_with_options(&valid_path, &options)?;
let sheet = loaded.worksheet("Sheet1")?;
let cells = sheet.get_cells();

println!(
    "Loaded workbook with {} worksheet(s) and {} diagnostic issue(s).",
    loaded.get_worksheets().count(),
    loaded.get_load_diagnostics().issues().len()
);
