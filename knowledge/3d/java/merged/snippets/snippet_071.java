import com.aspose.threed.FileFormat;
import com.aspose.threed.Scene;
import com.aspose.threed.Stream;

FileInputStream stream = new FileInputStream(new File("input/cube.stl"));
Scene scene = new Scene();
FileFormat format = FileFormat.getFormatByExtension(".stl");
scene.open(Stream.wrap(stream), format);
stream.close();
