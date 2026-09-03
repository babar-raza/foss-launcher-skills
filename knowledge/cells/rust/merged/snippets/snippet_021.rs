let mut hyperlinks = links_sheet.get_hyperlinks();
let external_index = hyperlinks.add("A1", 1, 1, "https://example.com/docs?q=1")?;
let mut external_link = hyperlinks.get(external_index).expect("hyperlink should exist");
external_link.set_text_to_display("Docs");
external_link.set_screen_tip("External docs");

let mut defined_names = workbook.get_defined_names();
let global_index = defined_names.add("GlobalRange", "='Links'!$A$1:$D$5")?;
defined_names.get(global_index).expect("defined name should exist").set_hidden(true);
