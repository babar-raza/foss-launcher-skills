// Mirror the Info dictionary into an XMP packet, then add XMP-only fields
doc.SyncInfoToXMP()

xmp, _ := doc.XMP()
xmp.Keywords = []string{"finance", "report", "Q3"}
xmp.Custom = append(xmp.Custom, pdf.XMPProperty{
    Namespace: "http://ns.adobe.com/xap/1.0/mm/",
    Prefix:    "xmpMM",
    Name:      "DocumentID",
    Value:     "uuid:1234",
})
doc.SetXMP(xmp)
doc.Save("with-xmp.pdf")

// Read it back
got, _ := doc.XMP()
fmt.Println(got.Title, got.Authors, got.Keywords)

// Or take full control with a raw packet
doc.SetXMPRaw([]byte(`<?xpacket ...?>...`))
doc.ClearXMP() // remove the /Catalog/Metadata stream
