it('testSimpleGltfJson', () => {
        const gltfData = {
            "asset": {
                "version": "2.0",
                "generator": "test"
            },
            "scene": 0,
            "scenes": [
                {
                    "nodes": [0]
                }
            ],
            "nodes": [
                {
                    "name": "TestNode",
                    "mesh": 0
                }
            ],
            "meshes": [
                {
                    "name": "TestMesh",
                    "primitives": [
                        {
                            "attributes": {
                                "POSITION": 0
                            },
                            "mode": 4
                        }
                    ]
                }
            ],
            "accessors": [
                {
                    "bufferView": 0,
                    "componentType": 5126,
                    "count": 3,
                    "type": "VEC3"
                }
            ],
            "bufferViews": [
                {
                    "buffer": 0,
                    "byteOffset": 0,
                    "byteLength": 36
                }
            ],
            "buffers": [
                {
                    "byteLength": 36,
                    "uri": "data:application/octet-stream;base64,AAAAAAAAAAAAAAAAAACAPwAAAAAAAAAAAAAAAAAAgD8AAAAA"
                }
            ]
        };

        const scene = new Scene();
        const jsonString = JSON.stringify(gltfData);
        const stream = new Uint8Array(Buffer.from(jsonString, 'utf-8'));
        const options = new GltfLoadOptions();

        scene.openFromBuffer(stream, options);

        expect(scene.rootNode.childNodes.length).toBe(1);
        const node = scene.rootNode.childNodes[0];
        expect(node.name).toBe('TestNode');
        expect(node.entity).toBeDefined();
    })