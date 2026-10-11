deja, _ := doc.LoadFont("DejaVuSans.ttf")
doc.SetSVGFontResolver(func(family string, bold, italic bool) pdf.Font {
    if strings.EqualFold(family, "DejaVu Sans") {
        return deja
    }
    return nil // falls back to heuristic Standard 14 mapping
})
page.AddSVG("diagram-with-cyrillic.svg", rect)
