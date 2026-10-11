def test_tokenizer():
    with open('examples/fbx7400ascii/box.fbx', 'r') as f:
        content = f.read()

    tokenizer = FbxTokenizer(content)
    tokens = tokenizer.tokenize()

    print(f"Tokenized {len(tokens)} tokens")
    for i, token in enumerate(tokens[:20]):
        print(f"  {i}: {token}")

    return tokens