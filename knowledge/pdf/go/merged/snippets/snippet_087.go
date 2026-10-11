fdf, _ := doc.Form().ExportFDF()    // %FDF-1.2 … /FDF /Fields [ … ]
template.Form().ImportFDF(fdf)

xfdf, _ := doc.Form().ExportXFDF()  // <xfdf><fields><field name=…><value>…
template.Form().ImportXFDF(xfdf)
