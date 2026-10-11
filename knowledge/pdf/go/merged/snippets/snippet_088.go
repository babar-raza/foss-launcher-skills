doc := pdf.NewDocument(595, 842)
form := doc.Form()

// Single-widget fields
tf, _ := form.AddTextField(1, pdf.Rectangle{LLX: 50, LLY: 700, URX: 545, URY: 725}, "name")
tf.SetMaxLen(50)
tf.SetValue("Jane Doe")

cb, _ := form.AddCheckbox(1, pdf.Rectangle{LLX: 50, LLY: 660, URX: 70, URY: 680}, "subscribe")
cb.SetChecked(true)

combo, _ := form.AddComboBox(1, pdf.Rectangle{LLX: 50, LLY: 600, URX: 250, URY: 625}, "country",
    []pdf.ChoiceOption{{Value: "USA"}, {Value: "Canada"}})
combo.SetSelected(0)

// Radio group: widgets can span multiple pages
rb, _ := form.AddRadioGroup("plan", []pdf.RadioItem{
    {PageNum: 1, Rect: pdf.Rectangle{LLX: 50, LLY: 540, URX: 70, URY: 560}, Export: "basic"},
    {PageNum: 1, Rect: pdf.Rectangle{LLX: 50, LLY: 510, URX: 70, URY: 530}, Export: "premium"},
})
rb.Options()[0].SetSelected(true)

submit, _ := form.AddPushButton(1, pdf.Rectangle{LLX: 50, LLY: 460, URX: 200, URY: 490}, "submit", "Submit")

// Rich push-button appearance: hover/press captions + an icon, baked
// into /AP/N, /AP/R, /AP/D so the button reacts in any viewer.
submit.SetAppearance(pdf.ButtonAppearance{
    Caption:      "Submit",
    RolloverText: "Click to submit",
    DownText:     "Submitting…",
    IconPath:     "logo.png",
    IconPosition: pdf.ButtonIconAboveCaption,
    TextColor:    &pdf.Color{R: 1, G: 1, B: 1, A: 1},
    FaceColor:    &pdf.Color{R: 0.15, G: 0.20, B: 0.55, A: 1},
})

// Style a field: navy border + tint fill + navy text, all persisted
// as /MK, /BS, /DA and rendered straight into the widget /AP.
tf.SetStyle(pdf.FieldStyle{
    BorderColor:     &pdf.Color{R: 0.15, G: 0.20, B: 0.55, A: 1},
    BackgroundColor: &pdf.Color{R: 0.95, G: 0.96, B: 1.0, A: 1},
    TextColor:       &pdf.Color{R: 0.15, G: 0.20, B: 0.55, A: 1},
    BorderWidth:     1,
    TextSize:        12,
})

// Remove a field by name
form.RemoveField("subscribe")

doc.Save("form.pdf")
