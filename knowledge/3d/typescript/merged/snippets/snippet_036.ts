it('testUvLoading', () => {
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
                                "POSITION": 0,
                                "TEXCOORD_0": 1
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
                },
                {
                    "bufferView": 1,
                    "componentType": 5126,
                    "count": 3,
                    "type": "VEC2"
                }
            ],
            "bufferViews": [
                {
                    "buffer": 0,
                    "byteOffset": 0,
                    "byteLength": 36
                },
                {
                    "buffer": 0,
                    "byteOffset": 36,
                    "byteLength": 24
                }
            ],
            "buffers": [
                {
                    "byteLength": 60,
                    "uri": "data:application/octet-stream;base64,AAAAAAAAAAAAAAAAAACAPwAAAAAAAAAAAAAAAAAAgD8AAAAAAAAAAAAAAAAAAIA/AAAAAAAAAAAAAIA/"
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
        expect(node.entity).toBeDefined();
        
        const entity = node.entity;
        expect(entity).toBeDefined();
        
        if (entity && entity instanceof Geometry) {
            let hasUvs = false;
            for (const element of entity.vertexElements) {
                if (element instanceof VertexElementUV) {
                    hasUvs = true;
                    break;
                }
            }
            expect(hasUvs).toBe(true);
        }
    })