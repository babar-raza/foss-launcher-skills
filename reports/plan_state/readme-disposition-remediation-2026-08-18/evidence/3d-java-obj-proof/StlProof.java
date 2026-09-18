import com.aspose.threed.*;
import java.io.*;
import java.util.*;

public class StlProof {
    public static void main(String[] args) throws Exception {
        String stl = "solid test\n" +
            "facet normal 0 0 1\n outer loop\n  vertex 0 0 0\n  vertex 1 0 0\n  vertex 0 1 0\n endloop\nendfacet\n" +
            "endsolid test\n";
        File tmp = File.createTempFile("claude_stl_proof_", ".stl");
        tmp.deleteOnExit();
        try (FileWriter w = new FileWriter(tmp)) { w.write(stl); }

        Scene scene = Scene.fromFile(tmp.getAbsolutePath());
        int children = scene.getRootNode().getChildNodes().size();
        System.out.println("STL import (published jar): child nodes = " + children);
        if (children > 0) {
            Mesh mesh = (Mesh) scene.getRootNode().getChildNodes().get(0).getEntities().get(0);
            System.out.println("  control points = " + mesh.getControlPoints().size()
                + ", polygons = " + mesh.getPolygonCount());
        }

        Scene outScene = new Scene();
        Mesh m = new Mesh("T");
        m.addControlPoint(0,0,0); m.addControlPoint(1,0,0); m.addControlPoint(0,1,0);
        m.createPolygon(new int[]{0,1,2});
        outScene.getRootNode().createChildNode("N", m);
        File tmpOut = File.createTempFile("claude_stl_proof_out_", ".stl");
        tmpOut.deleteOnExit();
        outScene.save(tmpOut.getAbsolutePath());
        System.out.println("STL export (published jar): output bytes = " + tmpOut.length());
    }
}
