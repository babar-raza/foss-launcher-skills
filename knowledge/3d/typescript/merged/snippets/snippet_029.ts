it('testSimple', () => {
        const content = `
; Test
FBXHeaderExtension:  {
    FBXHeaderVersion: 1003
    Version: 7400
    Creator: "Test"
}
`;
        const tokenizer = new FbxTokenizer(content);
        const tokens = tokenizer.tokenize();

        expect(tokens.length).toBeGreaterThan(0);
    })