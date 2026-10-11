import { Scene } from './dist/aspose/threed';
import { GltfSaveOptions } from './dist/aspose/threed/formats/gltf';

const scene = new Scene();
scene.open('mesh.stl');

const opts = new GltfSaveOptions();
opts.binaryMode = false;
scene.save('mesh.gltf', opts);
