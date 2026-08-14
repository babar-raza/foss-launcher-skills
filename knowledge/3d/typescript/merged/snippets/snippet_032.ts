describe('testFbxTokenizer', () => {
    it('testTokenizer', () => {
        const token_path = '../foss.3d.python/examples/fbx7400ascii/box.fbx';

        if (require('fs').existsSync(token_path)) {
            const content = require('fs').readFileSync(token_path, 'utf8');

            const tokenizer = new FbxTokenizer(content);
            const tokens = tokenizer.tokenize();

            expect(tokens.length).toBeGreaterThan(0);
        } else {
            console.log(`Test skipped: File not found: ${token_path}`);
        }
    });
})