it('AddTextNote still writes no /AP: viewers draw their own icon', () => {
    const d = Document.New();
    d.AddPage(PageFormat.A4);
    const n = d.Pages[0].AddTextNote({ rect: [10, 10, 30, 30] });
    expect(n.Dict.has('AP')).toBe(false);
    expect(count(decodePng(d.Pages[0].ToImage()), dark)).toBeGreaterThan(0);
  })