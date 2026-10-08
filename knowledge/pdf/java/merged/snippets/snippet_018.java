import java.util.HashMap;
import java.util.Map;

try (Document doc = new Document("input.pdf")) {
    Map<String, Integer> counts = new HashMap<>();
    for (Page page : doc.getPages()) {
        for (Annotation a : page.getAnnotations()) {
            String key = a.getSubtype();
            counts.merge(key, 1, Integer::sum);
        }
    }
    counts.forEach((type, count) -> System.out.println(type + ": " + count));
}
