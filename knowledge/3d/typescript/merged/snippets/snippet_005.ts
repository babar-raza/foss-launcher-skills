import { PolygonModifier } from './dist/aspose/threed/entities';
import { Vector4 } from './dist/aspose/threed/utilities';

const controlPoints = [
  new Vector4(0, 0, 0, 1),
  new Vector4(1, 0, 0, 1),
  new Vector4(0, 1, 0, 1),
  new Vector4(1, 1, 0, 1),
];
const quad = [0, 1, 3, 2];

const triangles = PolygonModifier.triangulate(controlPoints, [quad]);
console.log(triangles.length); // 2
