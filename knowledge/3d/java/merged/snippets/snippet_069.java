import com.aspose.threed.Node;
import com.aspose.threed.PbrMaterial;
import com.aspose.threed.Scene;
import com.aspose.threed.Vector3;

Scene scene = Scene.fromFile("input/cube.stl");
Node node = scene.getRootNode().getChildNodes().get(0);

PbrMaterial material = new PbrMaterial();
material.setAlbedo(new Vector3(0.8, 0.2, 0.2));
material.setMetallicFactor(0.1);
material.setRoughnessFactor(0.6);
node.setMaterial(material);

scene.save("output.stl");
