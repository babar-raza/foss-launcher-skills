doc, _ := pdf.Open("template.pdf")

// Iterate every form field
for _, f := range doc.Form().Fields() {
    fmt.Printf("%s = %q (type %v)\n", f.FullName(), f.Value(), pdf.FieldType(f))
}

// Set values by type
text := doc.Form().Field("name").(*pdf.TextBoxField)
text.SetValue("Jane Doe")

check := doc.Form().Field("subscribe").(*pdf.CheckboxField)
check.SetChecked(true)

radio := doc.Form().Field("plan").(*pdf.RadioButtonField)
radio.Options()[1].SetSelected(true)

combo := doc.Form().Field("country").(*pdf.ComboBoxField)
combo.SetSelected(0) // by index into combo.Options()

list := doc.Form().Field("interests").(*pdf.ListBoxField)
if list.MultiSelect() {
    list.SetSelected(0, 2, 3)
} else {
    list.SetSelected(1)
}

// Save — each widget already carries a pre-generated /AP appearance
doc.Save("filled.pdf")
