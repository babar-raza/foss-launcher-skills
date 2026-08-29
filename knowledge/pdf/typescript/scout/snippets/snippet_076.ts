it('preserves an appearance stream byte-for-byte', () => {
      const src = Document.Open(buildAnnotRoundtrip());
      // Give the square a real appearance, so there is one to preserve.
      const hi = src.Pages[0].Annotations.find((a) => a.Subtype === 'Highlight')!;
      const before = apBytes(src, hi.Dict);
      expect(before).toBeUndefined();   // the fixture ships without one

      // Regenerate one via the import path, export it, and re-import.
      const staged = clearedTarget();
      importData(staged, format, exportData(src, format, true), true);
      const stagedHi = staged.Pages[0].Annotations.find((a) => a.Subtype === 'Highlight')!;
      const generated = apBytes(staged, stagedHi.Dict);
      expect(generated).toBeDefined();

      const dst = clearedTarget();
      importData(dst, format, exportData(staged, format, true), true);
      const finalHi = dst.Pages[0].Annotations.find((a) => a.Subtype === 'Highlight')!;
      expect(apBytes(dst, finalHi.Dict)).toEqual(generated);
    })