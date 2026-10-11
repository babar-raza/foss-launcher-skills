import { Vector3, Quaternion, Matrix4 } from './dist/aspose/threed/utilities';

const v = new Vector3(1.0, 2.0, 3.0);
const q = new Quaternion(1.0, 0.0, 0.0, 0.0);
const m = new Matrix4();

console.log(v.length, q.length, m.determinant);
