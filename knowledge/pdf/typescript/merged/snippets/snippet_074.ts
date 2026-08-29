it('preserves the text note author and contents', () => {
      const { dst } = roundTrip();
      const note = dst.Pages[0].Annotations.find((a) => a.Subtype === 'Text')!;
      expect(note.Contents).toBe('a note');
      expect(note.Dict.has('T')).toBe(true);
    })