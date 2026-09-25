import com.aspose.threed.Box;
import com.aspose.threed.Scene;

Scene scene = new Scene();
Box box = new Box(2.0, 2.0, 2.0);
scene.getRootNode().createChildNode("box", box);
scene.save("box.stl");
