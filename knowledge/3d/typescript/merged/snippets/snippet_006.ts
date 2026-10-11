import { Scene } from './dist/aspose/threed';
import { Mesh } from './dist/aspose/threed/entities';
import { Vector3, Vector4 } from './dist/aspose/threed/utilities';
import { PhongMaterial } from './dist/aspose/threed/shading';

const scene = new Scene();
const mesh = new Mesh('TestMesh');
mesh.controlPoints.push(new Vector4(0.0, 0.0, 0.0, 1.0));
mesh.controlPoints.push(new Vector4(1.0, 0.0, 0.0, 1.0));
mesh.controlPoints.push(new Vector4(0.0, 1.0, 0.0, 1.0));
mesh.createPolygon(0, 1, 2);

const material = new PhongMaterial('RedMaterial');
material.diffuseColor = new Vector3(1.0, 0.0, 0.0);
material.specularColor = new Vector3(1.0, 1.0, 1.0);
material.shininess = 32.0;

const node = scene.rootNode.createChildNode('TestNode');
node.entity = mesh;
node.material = material;

scene.save('scene.dae');
