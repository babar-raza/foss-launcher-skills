import { Scene } from './dist/aspose/threed';
import { Mesh } from './dist/aspose/threed/entities';
import { PbrMaterial } from './dist/aspose/threed/shading';
import { Vector3, Vector4 } from './dist/aspose/threed/utilities';

const scene = new Scene();
const material = new PbrMaterial('red_metal');
material.albedo = new Vector3(1.0, 0.0, 0.0);
material.metallicFactor = 0.8;
material.roughnessFactor = 0.3;

const mesh = new Mesh('cube');
mesh.controlPoints = [
  new Vector4(0, 0, 0, 1), new Vector4(1, 0, 0, 1),
  new Vector4(1, 1, 0, 1), new Vector4(0, 1, 0, 1),
];
mesh.createPolygon(0, 1, 2, 3);

const node = scene.rootNode.createChildNode('cube');
node.entity = mesh;
node.material = material;
