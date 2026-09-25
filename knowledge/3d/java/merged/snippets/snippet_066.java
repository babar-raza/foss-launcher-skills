import com.aspose.threed.Scene;

// Load an STL file (format is detected automatically)
Scene scene = Scene.fromFile("input/cube.stl");

// Save it back out
scene.save("output.stl");
