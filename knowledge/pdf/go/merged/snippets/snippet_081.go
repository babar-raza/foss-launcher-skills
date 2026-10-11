// Read (the /Info dictionary; mirrors Aspose.PDF for .NET's Document.Info)
doc, _ := pdf.Open("input.pdf")
info, _ := doc.Info()
fmt.Println(info.Title, info.Author, info.CreationDate)

// Write (full replacement — unset fields are omitted from the PDF)
doc.SetInfo(pdf.DocumentInfo{
    Title:  "My Document",
    Author: "Jane Smith",
    Custom: map[string]string{"Department": "Legal"},
})
doc.Save("output.pdf")

// Update a single field: read → modify → write
info, _ = doc.Info()
info.Title = "Updated Title"
doc.SetInfo(info)

// Strip all metadata
doc.ClearInfo()
doc.Save("clean.pdf")
