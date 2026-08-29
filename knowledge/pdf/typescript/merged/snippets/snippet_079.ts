it('relinks the popup and the reply', () => {
      const { dst } = roundTrip();
      const note = dst.Pages[0].Annotations.find((a) => a.Subtype === 'Text')!;
      const hi = dst.Pages[0].Annotations.find((a) => a.Subtype === 'Highlight')!;
      expect(isDict(dst.resolve(note.Dict.get('Popup')))).toBe(true);
      expect(dst.resolve(hi.Dict.get('IRT'))).toBe(note.Dict);
    })