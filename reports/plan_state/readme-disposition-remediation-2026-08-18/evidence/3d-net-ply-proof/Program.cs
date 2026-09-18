using System;
using System.IO;
using System.Linq;
using Aspose.ThreeD;
using Aspose.ThreeD.Entities;
using Aspose.ThreeD.Formats;

int failures = 0;

void Section(string title) => Console.WriteLine($"\n=== {title} ===");

void Assert(bool cond, string msg)
{
    if (cond) { Console.WriteLine($"  PASS: {msg}"); }
    else { Console.WriteLine($"  FAIL: {msg}"); failures++; }
}

string tmpPly = Path.Combine(Path.GetTempPath(), "claude_ply_proof_" + Guid.NewGuid().ToString("N") + ".ply");

try
{
    // ---------------------------------------------------------------
    // TEST 1: Export via the public, extension-based Scene.Save API
    // ---------------------------------------------------------------
    Section("TEST 1: Scene.Save(\"file.ply\") export via public API");
    var scene = new Scene();
    // PlyWriter only walks literal Mesh entities (verified by reading PlyWriter.cs --
    // CollectVertices/WriteFacesRecursive both check `entity is Mesh`, with no
    // IMeshConvertible/ToMesh fallback, unlike ObjWriter/ColladaWriter/Discreet3DSWriter).
    // Use the same explicit ToMesh() a Box-to-PLY export therefore requires.
    var boxMesh = new Box(2, 3, 4).ToMesh();
    scene.RootNode.CreateChildNode("Box", boxMesh);

    scene.Save(tmpPly);

    var fi = new FileInfo(tmpPly);
    Assert(fi.Exists, "output file was created");
    Assert(fi.Length > 0, $"output file is non-empty ({(fi.Exists ? fi.Length : 0)} bytes)");

    var header = File.ReadLines(tmpPly).Take(1).FirstOrDefault() ?? "";
    Assert(header.Trim() == "ply", $"file starts with the PLY magic header (got: '{header.Trim()}')");

    // ---------------------------------------------------------------
    // TEST 2: Import that exact file back via the public API, verify
    // geometry survived the round trip.
    // ---------------------------------------------------------------
    Section("TEST 2: Scene.Open(\"file.ply\") import of the file just written");
    var reloaded = new Scene();
    reloaded.Open(tmpPly);

    var node = reloaded.RootNode.ChildNodes.FirstOrDefault();
    Assert(node != null, "reloaded scene has a child node");
    var mesh = node?.Entities.FirstOrDefault() as Mesh;
    Assert(mesh != null, "reloaded node's entity is a Mesh");
    Assert(mesh != null && mesh.ControlPoints.Count == 8, $"reloaded mesh has the box's 8 control points (got: {mesh?.ControlPoints.Count})");
    Assert(mesh != null && mesh.PolygonCount == 6, $"reloaded mesh has the box's 6 polygons (got: {mesh?.PolygonCount})");

    // ---------------------------------------------------------------
    // TEST 3: Import an independently hand-authored PLY fixture
    // (not produced by this library) via the public API.
    // ---------------------------------------------------------------
    Section("TEST 3: Scene.Open on an independently-authored PLY fixture (ASCII, single triangle)");
    string handAuthoredPly =
        "ply\n" +
        "format ascii 1.0\n" +
        "element vertex 3\n" +
        "property float x\n" +
        "property float y\n" +
        "property float z\n" +
        "element face 1\n" +
        "property list uchar int vertex_indices\n" +
        "end_header\n" +
        "0 0 0\n" +
        "1 0 0\n" +
        "0 1 0\n" +
        "3 0 1 2\n";
    // ---------------------------------------------------------------
    // TEST 3b (discovery, not part of G-52's own claim): confirm the
    // silent-empty-export behavior for a raw Primitive never converted
    // to Mesh -- PlyWriter.cs's CollectVertices/WriteFacesRecursive only
    // match `entity is Mesh`, no IMeshConvertible/ToMesh fallback, unlike
    // ObjWriter/ColladaWriter/Discreet3DSWriter. Not a thrown exception --
    // silent 0-vertex/0-face output. Logged as INFO, not asserted, since
    // it's outside G-52's own scope but worth recording as a real finding.
    // ---------------------------------------------------------------
    Section("TEST 3b (discovery): Scene.Save(\".ply\") on a raw, unconverted Primitive (Box)");
    {
        var rawScene = new Scene();
        rawScene.RootNode.CreateChildNode("Box", new Box(1, 1, 1)); // raw Primitive, not .ToMesh()
        string tmpPly3 = Path.Combine(Path.GetTempPath(), "claude_ply_proof_rawprim_" + Guid.NewGuid().ToString("N") + ".ply");
        try
        {
            rawScene.Save(tmpPly3);
            var content = File.ReadAllText(tmpPly3);
            Console.WriteLine($"  INFO: no exception thrown; output file has {new FileInfo(tmpPly3).Length} bytes");
            Console.WriteLine("  INFO: header lines:");
            foreach (var line in File.ReadLines(tmpPly3).Take(9)) Console.WriteLine("    " + line);
        }
        finally
        {
            if (File.Exists(tmpPly3)) File.Delete(tmpPly3);
        }
    }

    string tmpPly2 = Path.Combine(Path.GetTempPath(), "claude_ply_proof_fixture_" + Guid.NewGuid().ToString("N") + ".ply");
    File.WriteAllText(tmpPly2, handAuthoredPly);
    try
    {
        var fixtureScene = new Scene();
        fixtureScene.Open(tmpPly2);
        var fnode = fixtureScene.RootNode.ChildNodes.FirstOrDefault();
        Assert(fnode != null, "fixture scene has a child node");
        var fmesh = fnode?.Entities.FirstOrDefault() as Mesh;
        Assert(fmesh != null, "fixture node's entity is a Mesh");
        Assert(fmesh != null && fmesh.ControlPoints.Count == 3, $"fixture mesh has 3 vertices (got: {fmesh?.ControlPoints.Count})");
        Assert(fmesh != null && fmesh.PolygonCount == 1, $"fixture mesh has 1 polygon (got: {fmesh?.PolygonCount})");
    }
    finally
    {
        if (File.Exists(tmpPly2)) File.Delete(tmpPly2);
    }

    // ---------------------------------------------------------------
    // TEST 4: Document the ACTUAL failure mode of FileFormat.PLY /
    // Formats.PlyFormat.Encode/Decode -- the public static field the
    // candidate README's claim is (mis)sourced from.
    // ---------------------------------------------------------------
    Section("TEST 4: FileFormat.PLY (Formats.PlyFormat) direct Encode/Decode -- confirm broken, capture exact exception");
    try
    {
        var scene2 = new Scene();
        scene2.RootNode.CreateChildNode("Box", new Box(1, 1, 1));
        using var ms = new MemoryStream();
        FileFormat.PLY.Encode(scene2.RootNode.ChildNodes[0].Entities[0], ms);
        Assert(false, "FileFormat.PLY.Encode should have thrown but did not");
    }
    catch (Exception ex)
    {
        Assert(ex is NotImplementedException, $"FileFormat.PLY.Encode() throws {ex.GetType().Name}: \"{ex.Message}\"");
    }

    try
    {
        FileFormat.PLY.Decode(tmpPly);
        Assert(false, "FileFormat.PLY.Decode should have thrown but did not");
    }
    catch (Exception ex)
    {
        Assert(ex is NotImplementedException, $"FileFormat.PLY.Decode() throws {ex.GetType().Name}: \"{ex.Message}\"");
    }

    // ---------------------------------------------------------------
    // TEST 5: Does passing the public FileFormat.PLY object into
    // Scene.Save(stream, format) work, or does it also fail (and how)?
    // This is the exact confusion a developer reading "FileFormat.PLY"
    // in the API and reaching for it directly would hit.
    // ---------------------------------------------------------------
    Section("TEST 5: Scene.Save(stream, FileFormat.PLY) -- explicit public-field format object");
    try
    {
        var scene3 = new Scene();
        scene3.RootNode.CreateChildNode("Box", new Box(1, 1, 1));
        using var ms2 = new MemoryStream();
        scene3.Save(ms2, FileFormat.PLY);
        Assert(false, "Scene.Save(stream, FileFormat.PLY) should have thrown but did not");
    }
    catch (Exception ex)
    {
        Console.WriteLine($"  INFO: Scene.Save(stream, FileFormat.PLY) throws {ex.GetType().Name}: \"{ex.Message}\"");
    }
}
finally
{
    if (File.Exists(tmpPly)) File.Delete(tmpPly);
}

Console.WriteLine($"\n=== SUMMARY: {(failures == 0 ? "ALL ASSERTIONS PASSED" : $"{failures} ASSERTION(S) FAILED")} ===");
Environment.Exit(failures == 0 ? 0 : 1);
