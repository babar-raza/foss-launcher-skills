import com.aspose.threed.*;
import java.io.*;
import java.util.*;

public class ObjProof {
    static int failures = 0;

    static void section(String s) { System.out.println("\n=== " + s + " ==="); }

    static void check(boolean cond, String msg) {
        if (cond) System.out.println("  PASS: " + msg);
        else { System.out.println("  FAIL: " + msg); failures++; }
    }

    public static void main(String[] args) throws Exception {
        // A minimal, real, hand-authored OBJ file -- a single triangle. Not produced by this
        // library, so this independently tests the real OBJ import parser.
        String objText =
            "# simple triangle\n" +
            "v 0.0 0.0 0.0\n" +
            "v 1.0 0.0 0.0\n" +
            "v 0.0 1.0 0.0\n" +
            "f 1 2 3\n";
        File tmpObj = File.createTempFile("claude_obj_proof_", ".obj");
        tmpObj.deleteOnExit();
        try (FileWriter w = new FileWriter(tmpObj)) {
            w.write(objText);
        }

        section("TEST 1: Scene.fromFile(\"x.obj\") import via public API, independently-authored fixture");
        try {
            Scene scene = Scene.fromFile(tmpObj.getAbsolutePath());
            check(scene != null, "Scene.fromFile did not throw");
            List<Node> children = scene.getRootNode().getChildNodes();
            check(children.size() > 0, "scene has at least one child node (got " + children.size() + ")");
            if (children.size() > 0) {
                Node node = children.get(0);
                List<Entity> entities = node.getEntities();
                check(entities.size() > 0, "node has at least one entity (got " + entities.size() + ")");
                if (entities.size() > 0 && entities.get(0) instanceof Mesh) {
                    Mesh mesh = (Mesh) entities.get(0);
                    System.out.println("  INFO: control points = " + mesh.getControlPoints().size()
                        + ", polygons = " + mesh.getPolygonCount());
                    check(mesh.getControlPoints().size() == 3, "mesh has the 3 real vertices from the OBJ file");
                    check(mesh.getPolygonCount() == 1, "mesh has the 1 real face from the OBJ file");
                } else {
                    check(false, "first entity is a Mesh");
                }
            }
        } catch (Exception ex) {
            check(false, "Scene.fromFile threw: " + ex.getClass().getSimpleName() + ": " + ex.getMessage());
        }

        section("TEST 2: Scene.save(\"x.obj\") export via public API -- confirm claimed non-functional");
        try {
            Scene scene = new Scene();
            Mesh mesh = new Mesh("TestMesh");
            mesh.addControlPoint(0, 0, 0);
            mesh.addControlPoint(1, 0, 0);
            mesh.addControlPoint(0, 1, 0);
            mesh.createPolygon(new int[]{0, 1, 2});
            scene.getRootNode().createChildNode("TestNode", mesh);

            File tmpOut = File.createTempFile("claude_obj_proof_out_", ".obj");
            tmpOut.deleteOnExit();
            scene.save(tmpOut.getAbsolutePath());
            long len = tmpOut.length();
            System.out.println("  INFO: no exception thrown; output file has " + len + " bytes");
            check(len == 0, "output file is empty (0 bytes) -- confirms OBJ export is a real no-op stub, not a working exporter");
        } catch (Exception ex) {
            System.out.println("  INFO: Scene.save(\".obj\") threw " + ex.getClass().getSimpleName() + ": " + ex.getMessage());
        }

        section("TEST 3: Scene.fromFile(\"x.gltf\") import -- confirm claimed non-functional (stub returns empty scene)");
        {
            String gltfText = "{\"asset\":{\"version\":\"2.0\"}}";
            File tmpGltf = File.createTempFile("claude_gltf_proof_", ".gltf");
            tmpGltf.deleteOnExit();
            try (FileWriter w = new FileWriter(tmpGltf)) { w.write(gltfText); }
            Scene scene = Scene.fromFile(tmpGltf.getAbsolutePath());
            int childCount = scene.getRootNode().getChildNodes().size();
            System.out.println("  INFO: no exception thrown; child node count = " + childCount);
            check(childCount == 0, "glTF import returns an empty scene -- confirms stub behavior as claimed");
        }

        System.out.println("\n=== SUMMARY: " + (failures == 0 ? "ALL ASSERTIONS PASSED" : failures + " ASSERTION(S) FAILED") + " ===");
        System.exit(failures == 0 ? 0 : 1);
    }
}
