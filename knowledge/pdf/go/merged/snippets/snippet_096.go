doc := pdf.NewDocument(595, 842)
page, _ := doc.Page(1)

// Stroke a dashed red line.
page.DrawLine(
    pdf.Point{X: 50, Y: 700}, pdf.Point{X: 545, Y: 700},
    pdf.LineStyle{
        Color:       &pdf.Color{R: 1, G: 0, B: 0, A: 1},
        Width:       2,
        DashPattern: []float64{6, 3},
    },
)

// Fill a rounded box with semi-transparent blue.
page.DrawRoundedRectangle(
    pdf.Rectangle{LLX: 100, LLY: 500, URX: 400, URY: 600}, 10,
    pdf.ShapeStyle{
        LineStyle: pdf.LineStyle{Width: 1, Color: &pdf.Color{R: 0, G: 0, B: 0.5, A: 1}},
        FillColor: &pdf.Color{R: 0.6, G: 0.8, B: 1, A: 0.5},
    },
)

// Custom path: shape with curve and close.
path := pdf.NewPath().
    MoveTo(200, 300).
    LineTo(400, 300).
    CurveTo(420, 320, 420, 360, 400, 380).
    LineTo(200, 380).
    Close()
page.DrawPath(path, pdf.ShapeStyle{
    LineStyle: pdf.LineStyle{Width: 1.5},
    FillColor: &pdf.Color{R: 1, G: 0.9, B: 0.3, A: 1},
})

// Gradient fills — linear (left→right) and radial (off-centre highlight).
red := pdf.Color{R: 0.9, G: 0.1, B: 0.1, A: 1}
blue := pdf.Color{R: 0.1, G: 0.2, B: 0.8, A: 1}
white := pdf.Color{R: 1, G: 1, B: 1, A: 1}

page.DrawRectangle(pdf.Rectangle{LLX: 50, LLY: 200, URX: 250, URY: 280},
    pdf.ShapeStyle{FillGradient: pdf.NewLinearGradient(50, 0, 250, 0,
        pdf.GradientStop{Offset: 0, Color: red},
        pdf.GradientStop{Offset: 1, Color: blue})})

page.DrawCircle(pdf.Point{X: 150, Y: 100}, 60, pdf.ShapeStyle{
    FillGradient: pdf.RadialGradient{
        CX: 150, CY: 100, R: 60, FX: 130, FY: 125, // focal up-left → 3D sphere
        Stops: []pdf.GradientStop{{0, white}, {1, blue}}}})

doc.Save("shapes.pdf")
