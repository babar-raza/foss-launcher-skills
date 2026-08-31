import { Scene } from './dist/aspose/threed';
import { GltfLoadOptions } from './dist/aspose/threed/formats/gltf';
import { PbrMaterial } from './dist/aspose/threed/shading';
import * as fs from 'fs';

const scene = new Scene();
const options = new GltfLoadOptions();
const buffer = fs.readFileSync('model.gltf');
scene.openFromBuffer(buffer, options);

const node = scene.rootNode.childNodes[0];
if (node.material instanceof PbrMaterial) {
  console.log(node.material.name, node.material.metallicFactor, node.material.roughnessFactor);
}
