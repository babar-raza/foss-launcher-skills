def test_simple():
    content = '''
; Test
FBXHeaderExtension:  {
    FBXHeaderVersion: 1003
    Version: 7400
    Creator: "Test"
}
'''
    tokenizer = FbxTokenizer(content)
    tokens = tokenizer.tokenize()

    print(f"Tokenized {len(tokens)} tokens")
    for i, token in enumerate(tokens):
        print(f"  {i}: {token}")