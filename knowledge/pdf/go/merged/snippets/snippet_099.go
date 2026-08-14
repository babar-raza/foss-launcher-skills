doc, _ := pdf.Open("filled-form.pdf")

// Flatten the whole form (removes every field and the /AcroForm dict)
doc.Flatten()                 // convenience for doc.Form().Flatten()

// …or flatten a single field, leaving the rest of the form interactive
doc.Form().Field("signature").Flatten()

// Flatten one annotation, or every (non-widget) annotation on a page
page, _ := doc.Page(1)
page.Annotations().At(0).Flatten()
page.Annotations().Flatten()

doc.Save("flattened.pdf")
