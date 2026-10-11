def test_parser(tokens):
    parser = FbxParser(tokens)
    print(f"\nParsed root scope with {len(parser.root_scope.elements)} top-level elements")

    for key in list(parser.root_scope.elements.keys())[:10]:
        elements = parser.root_scope.get_elements(key)
        print(f"  {key}: {len(elements)} element(s)")