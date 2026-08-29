it('survives a Save/Open cycle', () => {
      const { dst } = roundTrip();
      const reopened = Document.Open(dst.Save());
      expect(reopened.Pages[0].Annotations.length).toBe(3);
      expect(reopened.Pages[1].Annotations.length).toBe(1);
      const note = reopened.Pages[0].Annotations.find((a) => a.Subtype === 'Text')!;
      expect(note.Contents).toBe('a note');
    })