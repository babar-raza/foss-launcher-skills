import { Scene } from './dist/aspose/threed';
import { ObjLoadOptions } from './dist/aspose/threed/formats/obj';

const scene = new Scene();
const options = new ObjLoadOptions();
options.enableMaterials = true;
scene.open('model.obj', options);

for (const node of scene.rootNode.childNodes) {
  if (node.entity) {
    console.log(`Node: ${node.name}`);
  }
}
