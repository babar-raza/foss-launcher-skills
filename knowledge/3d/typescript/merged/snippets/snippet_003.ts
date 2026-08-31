import { Scene, Node } from './dist/aspose/threed';
import { Mesh } from './dist/aspose/threed/entities';
import { Vector4 } from './dist/aspose/threed/utilities';

const scene = new Scene();
const mesh = new Mesh('triangle');
mesh.controlPoints = [
  new Vector4(0.0, 0.0, 0.0, 1.0),
  new Vector4(1.0, 0.0, 0.0, 1.0),
  new Vector4(1.0, 1.0, 0.0, 1.0),
];
mesh.createPolygon(0, 1, 2);

const node = new Node('triangle_node');
node.entity = mesh;
node.parentNode = scene.rootNode;

scene.save('triangle.stl');
