describe('testImports', () => {
    it('testModuleImports', () => {
        const { Scene, Node, Light } = require('../src/aspose/threed');
        const { Vector3, Matrix4 } = require('../src/aspose/threed/utilities');

        const scene = new Scene();
        const node = new Node("test_node");

        const vec = new Vector3(1.0, 2.0, 3.0);

        const mat = new Matrix4();

        const light = new Light("test_light");

        expect(scene).toBeDefined();
        expect(node).toBeDefined();
        expect(vec).toBeDefined();
        expect(mat).toBeDefined();
        expect(light).toBeDefined();
    });
})