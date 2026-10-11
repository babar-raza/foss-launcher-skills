fn main() -> Result<(), Box<dyn Error>> {
    let output_path = common::output_path("document-properties-sample.xlsx");

    let mut workbook = Workbook::new();
    {
        let mut worksheets = workbook.get_worksheets_mut();
        let sheet = worksheets.get(0)?;
        sheet.set_name("Sample")?;
        let mut cells = sheet.get_cells_mut();
        cells.get("A1")?.put_value_string("Title")?;
        cells
            .get("B1")?
            .put_value_string("Document Properties Sample")?;
    }

    {
        let properties = workbook.get_document_properties_mut();
        properties.set_title("Annual Sales Report 2024");
        properties.set_subject("Financial Performance Analysis");
        properties.set_author("Finance Department");
        properties.set_keywords("sales, finance, 2024, report");
        properties.set_comments("This document contains quarterly sales data and projections");
        properties.set_category("Financial Reports");
        properties.set_company("Acme Corporation");
        properties.set_manager("Jane Smith");

        let core = properties.get_core_mut();
        core.set_creator("Finance Department");
        core.set_last_modified_by("Finance Department");
        core.set_created(Some(Utc::now()));

        let extended = properties.get_extended_mut();
        extended.set_company("Acme Corporation");
        extended.set_manager("Jane Smith");
    }

    workbook.save(&output_path)?;

    let loaded = Workbook::load_xlsx(&output_path)?;
    let properties = loaded.get_document_properties();

    println!("Saved: {}", output_path.display());
    println!("Title: {}", properties.get_title());
    println!("Subject: {}", properties.get_subject());
    println!("Author: {}", properties.get_author());
    println!("Keywords: {}", properties.get_keywords());
    println!("Comments: {}", properties.get_comments());
    println!("Category: {}", properties.get_category());
    println!("Company: {}", properties.get_company());
    println!("Manager: {}", properties.get_manager());
    println!("Core Creator: {}", properties.get_core().get_creator());
    println!(
        "Core LastModifiedBy: {}",
        properties.get_core().get_last_modified_by()
    );
    println!(
        "Extended Company: {}",
        properties.get_extended().get_company()
    );
    println!(
        "Extended Manager: {}",
        properties.get_extended().get_manager()
    );

    Ok(())
}