import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

try (InputStream in = fs.getContents()) {
    if (in != null) {
        Files.copy(in, Path.of("extracted", fs.getName()));
    }
}
