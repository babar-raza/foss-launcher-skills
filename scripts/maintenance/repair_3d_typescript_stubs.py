#!/usr/bin/env python3
"""
Expand 3D TypeScript reference stubs — add prose to Overview sections
and descriptions to empty method/property table cells.
Grounded in knowledge/3d/typescript/merged/api_surface.md.
"""

import re
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "pipeline"))
from provenance import update_mechanism

BASE = Path("D:/onedrive/Documents/GitHub/aspose.org")
REF_DIR = BASE / "content/reference.aspose.org/en/3d/typescript"

# -----------------------------------------------------------------------
# Class-level overview prose, grounded in API surface knowledge.
# -----------------------------------------------------------------------
CLASS_OVERVIEWS = {
    "A3DObject": (
        "`A3DObject` is the base class for all named objects in Aspose.3D. "
        "It provides a common identity (`name`) and a dynamic property bag (`properties`) "
        "that lets callers attach arbitrary metadata to any 3D object. "
        "Extend or hold a reference to `A3DObject` whenever you need named, property-aware objects in the scene."
    ),
    "AnimationChannel": (
        "`AnimationChannel` links a single animated property component to a `KeyframeSequence`. "
        "It records the component type and default value so the animation system can interpolate "
        "the channel over time. "
        "Use `AnimationNode` to obtain channels rather than constructing them directly."
    ),
    "AnimationClip": (
        "`AnimationClip` is a self-contained animation segment with a defined start and stop time. "
        "It holds one or more `AnimationNode` objects that drive scene-object properties over that range. "
        "Attach a clip to a `Scene` with `createAnimationClip` and select it via `currentAnimationClip` "
        "to control which animation is active."
    ),
    "AnimationNode": (
        "`AnimationNode` is the per-object container for keyframe data in the animation system. "
        "It holds `BindPoint` entries that connect scene-object properties to `KeyframeSequence` curves, "
        "and may contain nested `subAnimations` for hierarchical rigs. "
        "Retrieve or create an `AnimationNode` through `AnimationClip.createAnimationNode`."
    ),
    "ApertureMode": (
        "`ApertureMode` is an enumeration that controls how a camera's field of view is calculated "
        "when both horizontal and vertical aperture sizes are specified. "
        "Choose `HORIZONTAL`, `VERTICAL`, or `HORZ_AND_VERT` depending on which axis should drive the FOV."
    ),
    "AssetInfo": (
        "`AssetInfo` stores document-level metadata for a 3D scene, such as creator, creation date, "
        "and unit information. "
        "Access it through `Scene.assetInfo` to read or write file-level attributes before saving."
    ),
    "Axis": (
        "`Axis` is an enumeration of the six coordinate-system axes (positive and negative X, Y, Z). "
        "It is used wherever an API requires an explicit axis direction, for example when setting "
        "up-axis conventions during import or export."
    ),
    "BinaryTokenizer": (
        "`BinaryTokenizer` parses a raw byte buffer into a sequence of typed tokens for the FBX binary "
        "format reader. "
        "Call `tokenize()` on a `_data` buffer to obtain the token array that `FbxParser` consumes. "
        "This is an internal parsing helper; most applications work with the higher-level importer APIs."
    ),
    "BindPoint": (
        "`BindPoint` connects a scene-object `Property` to one or more `AnimationChannel` instances. "
        "It is the bridge between the property system and the keyframe system: calling "
        "`getKeyframeSequence` or `createKeyframeSequence` through a `BindPoint` associates "
        "animation curves with specific object properties. "
        "Obtain bind points via `AnimationNode.getBindPoint`."
    ),
    "BooleanOperation": (
        "`BooleanOperation` is an enumeration of constructive solid geometry (CSG) operations. "
        "Pass one of `ADD`, `SUB`, or `INTERSECT` to `Mesh.doBoolean` to combine two meshes "
        "using union, subtraction, or intersection respectively."
    ),
    "BoundingBox": (
        "`BoundingBox` represents an axis-aligned bounding box (AABB) in 3D space defined by "
        "a `minimum` and `maximum` corner. "
        "It provides helpers for merging boxes, testing containment and overlap, and computing "
        "the center and size. "
        "Retrieve a node or geometry's bounding box with the `getBoundingBox()` method."
    ),
    "BoundingBox2D": (
        "`BoundingBox2D` is a 2D axis-aligned bounding rectangle defined by `minimum` and `maximum` "
        "`Vector2` corners. "
        "It provides overlap testing, merging, and factory methods for null and infinite extents, "
        "useful for UV-space and screen-space calculations."
    ),
    "BoundingBoxExtent": (
        "`BoundingBoxExtent` describes the extent state of a `BoundingBox` — whether it is null "
        "(empty), finite, or infinite. "
        "Read the `extent` property on a `BoundingBox` to determine whether it contains valid geometry."
    ),
    "Camera": (
        "`Camera` is an entity that defines a viewpoint in the 3D scene. "
        "It exposes projection parameters such as `fieldOfView`, `nearPlane`, `farPlane`, and "
        "`projectionType` (perspective or orthographic), as well as orientation helpers like "
        "`lookAt`, `direction`, and `up`. "
        "Attach a `Camera` to a `Node` to position it in the scene graph."
    ),
    "ColladaExporter": (
        "`ColladaExporter` writes a `Scene` to the COLLADA (.dae) format. "
        "It is registered automatically through `ColladaPlugin` and is invoked by `Scene.save` "
        "when the target format is COLLADA. "
        "Use `ColladaSaveOptions` to control coordinate-system flipping, material export, and indentation."
    ),
    "ColladaFormat": (
        "`ColladaFormat` is the `FileFormat` descriptor for the COLLADA (.dae) interchange format. "
        "It exposes the MIME type, file extensions, and factory methods for creating "
        "`ColladaLoadOptions` and `ColladaSaveOptions`. "
        "Obtain the singleton with `ColladaFormat.getInstance()`."
    ),
    "ColladaFormatDetector": (
        "`ColladaFormatDetector` inspects an input stream or file name to determine whether "
        "it is a COLLADA file. "
        "It is registered in the `IOService` and called automatically during scene loading. "
        "Most applications do not need to instantiate it directly."
    ),
    "ColladaImporter": (
        "`ColladaImporter` reads a COLLADA (.dae) stream into a `Scene`. "
        "It is invoked automatically by `Scene.open` when a COLLADA file is detected. "
        "Pass a `ColladaLoadOptions` instance to control coordinate flipping, material loading, "
        "scale, and normal normalization."
    ),
    "ColladaLoadOptions": (
        "`ColladaLoadOptions` configures how COLLADA files are imported. "
        "Key settings include `flipCoordinateSystem` (convert from COLLADA's Y-up convention), "
        "`enableMaterials` (whether to parse material definitions), `scale` (uniform scale factor), "
        "and `normalizeNormal` (whether to normalise imported surface normals)."
    ),
    "ColladaPlugin": (
        "`ColladaPlugin` registers the COLLADA importer, exporter, format descriptor, and format "
        "detector with the `IOService`. "
        "Call `ColladaPlugin.getInstance()` to retrieve the singleton, which is registered "
        "automatically when the package is loaded."
    ),
    "ColladaSaveOptions": (
        "`ColladaSaveOptions` controls how a `Scene` is exported to the COLLADA format. "
        "Set `flipCoordinateSystem` to emit Y-up coordinates, `enableMaterials` to include material "
        "definitions, and `indented` to pretty-print the XML output."
    ),
    "ColladaTransformStyle": (
        "`ColladaTransformStyle` controls how node transforms are encoded in exported COLLADA files. "
        "`COMPONENTS` writes individual `<translate>`, `<rotate>`, and `<scale>` elements, "
        "while `MATRIX` writes a single `<matrix>` element."
    ),
    "ComposeOrder": (
        "`ComposeOrder` specifies how successive transforms are combined in a `TransformBuilder`. "
        "`APPEND` post-multiplies each new transform (right-to-left composition), "
        "while `PREPEND` pre-multiplies it (left-to-right composition)."
    ),
    "CustomObject": (
        "`CustomObject` is a general-purpose `A3DObject` subclass used to store arbitrary "
        "named objects in a scene's `library`. "
        "It has no built-in geometry or rendering semantics and serves as a flexible container "
        "for custom metadata or application-defined objects."
    ),
    "Entity": (
        "`Entity` is the abstract base class for all attachable scene components such as meshes, "
        "lights, and cameras. "
        "Entities are attached to `Node` objects via `Node.addEntity` and can report their "
        "bounding box through `getBoundingBox`. "
        "The `parentNode` and `parentNodes` properties expose the node hierarchy an entity belongs to."
    ),
    "Extrapolation": (
        "`Extrapolation` defines how a `KeyframeSequence` curve behaves before its first keyframe "
        "(`preBehavior`) or after its last keyframe (`postBehavior`). "
        "Set the `type` to one of the `ExtrapolationType` values and optionally set `repeatCount` "
        "for cycle-based behaviours."
    ),
    "ExtrapolationType": (
        "`ExtrapolationType` is an enumeration of curve extrapolation modes used by `Extrapolation`. "
        "Values include `CONSTANT` (hold the boundary value), `GRADIENT` (linear extrapolation), "
        "`CYCLE`, `CYCLE_RELATIVE`, and `OSCILLATE` (ping-pong)."
    ),
    "FMatrix4": (
        "`FMatrix4` is a 4×4 single-precision floating-point matrix used for transform and "
        "projection calculations. "
        "It supports concatenation, transposition, and inversion, and is the single-precision "
        "counterpart of the double-precision `Matrix4`."
    ),
    "FVector2": (
        "`FVector2` is a single-precision 2D vector with `x` and `y` components. "
        "It provides arithmetic operations (add, subtract, multiply, divide), length, "
        "normalisation, dot product, and parsing from a string. "
        "Use it for UV coordinates and 2D calculations that prefer `float` precision."
    ),
    "FVector3": (
        "`FVector3` is a single-precision 3D vector with `x`, `y`, and `z` components. "
        "It supplies factory methods for common unit vectors and supports normalisation, "
        "component access by index, equality testing, and string formatting. "
        "Use it for vertex data and other `float`-precision geometric calculations."
    ),
    "FVector4": (
        "`FVector4` is a single-precision 4D vector with `x`, `y`, `z`, and `w` components. "
        "It is used for homogeneous coordinates, tangent data, and colour channels that require "
        "`float` precision. "
        "Component access by index and equality comparison are supported."
    ),
    "FbxElement": (
        "`FbxElement` represents a parsed node in the FBX document tree. "
        "Each element has an optional `compound` child, a list of `tokens`, and helper methods "
        "`getFirstElement` and `getElements` for navigating child elements by name. "
        "It is an internal data structure used by `FbxParser` and `FbxImporter`."
    ),
    "FbxExporter": (
        "`FbxExporter` writes a `Scene` to the Autodesk FBX format. "
        "It is registered via `FbxPlugin` and invoked automatically by `Scene.save` for FBX targets. "
        "The `meshes` and `nodes` properties expose the geometry and scene-node data prepared during export."
    ),
    "FbxFormat": (
        "`FbxFormat` is the `FileFormat` descriptor for the Autodesk FBX interchange format. "
        "It reports the file extension, MIME type, import/export capabilities, and provides factory "
        "methods for `FbxLoadOptions` and `FbxSaveOptions`. "
        "Obtain the singleton with `FbxFormat.getInstance()`."
    ),
    "FbxFormatDetector": (
        "`FbxFormatDetector` inspects an input stream or file name to determine whether the "
        "file is in FBX format. "
        "It is registered in `IOService` and called automatically during scene loading."
    ),
    "FbxImporter": (
        "`FbxImporter` reads an FBX file or stream into a `Scene`. "
        "It supports both ASCII and binary FBX variants and is invoked automatically by `Scene.open`. "
        "Pass an `FbxLoadOptions` instance to control whether built-in global settings are retained."
    ),
    "FbxLoadOptions": (
        "`FbxLoadOptions` configures FBX import behaviour. "
        "Set `keepBuiltinGlobalSettings` to `true` to preserve the FBX file's global settings "
        "node verbatim rather than mapping it to Aspose.3D's scene model."
    ),
    "FbxParser": (
        "`FbxParser` converts a flat array of FBX tokens produced by `FbxTokenizer` or "
        "`BinaryTokenizer` into a hierarchical `FbxElement` tree. "
        "Call `parse(_data)` with a token array to get the root `FbxProperty`. "
        "This is an internal component of the FBX import pipeline."
    ),
    "FbxPlugin": (
        "`FbxPlugin` registers all FBX I/O components — importer, exporter, format, and "
        "format detector — with the `IOService`. "
        "Call `FbxPlugin.getInstance()` to retrieve the singleton; registration happens "
        "automatically when the package loads."
    ),
    "FbxProperty": (
        "`FbxProperty` holds a single named value within an FBX document. "
        "Each property has a `name`, a typed `value`, and an array of nested child `properties`. "
        "It is the leaf node type produced by `FbxParser`."
    ),
    "FbxSaveOptions": (
        "`FbxSaveOptions` configures how a scene is written to the FBX format. "
        "Set `embedTextures` to `true` to inline texture data directly in the FBX file "
        "rather than referencing external image files."
    ),
    "FbxTokenizer": (
        "`FbxTokenizer` converts ASCII FBX text content into a flat token array consumed by "
        "`FbxParser`. "
        "Call `tokenize()` on the content string to obtain the tokens. "
        "This is an internal component of the FBX ASCII import pipeline."
    ),
    "FileSystem": (
        "`FileSystem` is an abstraction layer for file I/O used during scene loading and saving. "
        "Factory methods create instances backed by local directories, ZIP archives, or a no-op "
        "dummy. "
        "Assign a `FileSystem` instance to `IOConfig.fileSystem` to redirect how the importer or "
        "exporter resolves relative file references such as textures."
    ),
    "Geometry": (
        "`Geometry` is the abstract base class for all renderable geometry types including `Mesh`. "
        "It manages a list of `controlPoints` (vertices) and `vertexElements` (per-vertex "
        "data channels such as normals, UVs, and colours). "
        "Use `addControlPoint`, `createElement`, and `createElementUV` to build geometry data "
        "before attaching the geometry to a `Node`."
    ),
    "GlobalTransform": (
        "`GlobalTransform` exposes the world-space transform of a `Node` as computed by evaluating "
        "the full parent chain. "
        "It provides read-only access to `translation`, `scale`, `eulerAngles`, `rotation`, and "
        "the combined `transformMatrix`. "
        "Access it through `Node.globalTransform` rather than constructing it directly."
    ),
    "GltfAccessor": (
        "`GltfAccessor` is a data-transfer object representing a glTF accessor, which describes "
        "how to interpret a region of a buffer view as typed attribute data. "
        "Properties include `bufferView` index, `byteOffset`, `componentType`, element `count`, "
        "`type` string, and optional `min`/`max` value arrays."
    ),
    "GltfBufferView": (
        "`GltfBufferView` is a data-transfer object representing a glTF buffer view — a slice "
        "of a binary buffer identified by `buffer` index, `byteOffset`, and `byteLength`. "
        "The `target` property indicates whether the view is used for vertex attributes or indices."
    ),
    "GltfData": (
        "`GltfData` is the root data-transfer object for a parsed glTF JSON document. "
        "It contains the scene index, scenes, nodes, meshes, accessors, buffer views, buffers, "
        "and materials as plain TypeScript arrays, reflecting the glTF 2.0 JSON structure directly."
    ),
    "GltfExporter": (
        "`GltfExporter` serialises a `Scene` to the glTF 2.0 format (`.gltf` or `.glb`). "
        "It is registered via `GltfPlugin` and called automatically by `Scene.save`. "
        "Use `GltfSaveOptions` to choose between JSON and binary modes and to control UV "
        "coordinate flipping."
    ),
    "GltfFormat": (
        "`GltfFormat` is the `FileFormat` descriptor for glTF 2.0. "
        "It reports the file extension, MIME type, import/export support, and provides factory "
        "methods for `GltfLoadOptions` and `GltfSaveOptions`. "
        "Obtain the singleton with `GltfFormat.getInstance()`."
    ),
    "GltfFormatDetector": (
        "`GltfFormatDetector` identifies whether an input stream or file name corresponds to "
        "a glTF or GLB file. "
        "It is registered in `IOService` and invoked automatically during scene loading."
    ),
    "GltfImporter": (
        "`GltfImporter` reads glTF 2.0 (.gltf / .glb) files into a `Scene`. "
        "After import the `json` property exposes the raw `GltfData` tree and `binary` holds "
        "the binary buffer when the GLB container format is used. "
        "Pass a `GltfLoadOptions` to control UV vertical flip."
    ),
    "GltfLoadOptions": (
        "`GltfLoadOptions` configures glTF import behaviour. "
        "Set `flipTexCoordV` to `true` to vertically flip UV coordinates, which is required "
        "when the target renderer uses a top-left UV origin (OpenGL vs. DirectX convention)."
    ),
    "GltfMaterial": (
        "`GltfMaterial` is a data-transfer object for a glTF material definition. "
        "It holds PBR metallic-roughness parameters (`pbrMetallicRoughness`), emissive factor, "
        "alpha mode, and alpha cutoff, mirroring the glTF 2.0 material specification."
    ),
    "GltfMesh": (
        "`GltfMesh` is a data-transfer object representing a named glTF mesh that contains "
        "one or more `GltfPrimitive` objects. "
        "Each primitive references accessor indices for vertex attributes and draw-call metadata."
    ),
    "GltfNode": (
        "`GltfNode` is a data-transfer object representing a single node in the glTF scene graph. "
        "It carries an optional mesh index, child node indices, and local transform data "
        "(translation, rotation, scale arrays)."
    ),
    "GltfPlugin": (
        "`GltfPlugin` registers all glTF I/O components with the `IOService`. "
        "Obtain the singleton with `GltfPlugin.getInstance()`; registration is automatic "
        "when the package is imported."
    ),
    "GltfPrimitive": (
        "`GltfPrimitive` is a data-transfer object for one draw call within a `GltfMesh`. "
        "The `attributes` map links semantic names (POSITION, NORMAL, TEXCOORD_0, etc.) to "
        "accessor indices, while `indices`, `material`, and `mode` define the topology."
    ),
    "GltfSaveOptions": (
        "`GltfSaveOptions` controls glTF export behaviour. "
        "Set `binaryMode` to `true` to produce a self-contained GLB binary container, "
        "or `false` for separate JSON and binary files. "
        "Use `flipTexCoordV` to adjust UV vertical orientation for the target renderer."
    ),
    "GltfScene": (
        "`GltfScene` is a data-transfer object representing a glTF scene — a list of root "
        "node indices that form the top of the scene graph hierarchy."
    ),
    "IIndexedVertexElement": (
        "`IIndexedVertexElement` is an interface that adds an `indices` array to a vertex element, "
        "enabling indexed (indirect) vertex data storage. "
        "Implement this interface when a vertex element uses `INDEX` or `INDEX_TO_DIRECT` "
        "reference mode."
    ),
    "INamedObject": (
        "`INamedObject` is the minimal interface for any object that has a `name` string property. "
        "It is the root interface implemented by `A3DObject` and, by extension, by all named "
        "3D scene objects."
    ),
    "IOConfig": (
        "`IOConfig` is the base configuration class for all import and export operations. "
        "It carries the target `fileFormat`, text `encoding`, a `fileSystem` abstraction for "
        "resolving external references, `lookupPaths`, and the source `fileName`. "
        "Specialised subclasses (`LoadOptions`, `SaveOptions`) extend it with format-specific settings."
    ),
    "IOExtension": (
        "`IOExtension` is an internal marker interface used by the I/O service to identify "
        "extensible format components. "
        "It has no public methods and is implemented by format plugins."
    ),
    "IOService": (
        "`IOService` is the central registry for all 3D format plugins. "
        "It maintains lists of registered importers, exporters, and format detectors, and "
        "provides lookup methods for resolving a file format from a stream or extension. "
        "Obtain the singleton with `IOService.instance()` and call `registerPlugin` to add "
        "a new format."
    ),
    "ImageRenderOptions": (
        "`ImageRenderOptions` configures the output dimensions for `Scene.render`. "
        "Set `width` and `height` (in pixels) to control the size of the rendered image."
    ),
    "Interpolation": (
        "`Interpolation` is an enumeration of keyframe interpolation modes for `KeyFrame`. "
        "Modes include `CONSTANT` (step), `LINEAR`, `BEZIER`, `B_SPLINE`, "
        "`CARDINAL_SPLINE`, and `TCB_SPLINE` (tension-continuity-bias)."
    ),
    "KeyFrame": (
        "`KeyFrame` stores one sample point on a `KeyframeSequence` animation curve. "
        "Each keyframe has a `time` position, a scalar `value`, an `interpolation` mode, "
        "and optional tangent/weight data for smooth interpolation. "
        "Add keyframes to a curve with `KeyframeSequence.add`."
    ),
    "KeyframeSequence": (
        "`KeyframeSequence` is an animation curve that maps time values to scalar outputs "
        "through a sorted list of `KeyFrame` objects. "
        "Set `preBehavior` and `postBehavior` via `Extrapolation` to control curve extension "
        "beyond the first and last keyframes. "
        "Obtain or create sequences through `BindPoint.createKeyframeSequence`."
    ),
    "LambertMaterial": (
        "`LambertMaterial` is a diffuse-only shading material that supports ambient, diffuse, "
        "emissive, and transparent colour components. "
        "It is the base class for `PhongMaterial` and corresponds to the Lambert shading model "
        "used in FBX and COLLADA files. "
        "Assign a `LambertMaterial` to `Node.material` to shade attached geometry."
    ),
    "Light": (
        "`Light` is an entity that emits light in the 3D scene. "
        "Set `lightType` to one of the `LightType` values — `POINT`, `DIRECTIONAL`, `SPOT`, "
        "`AREA`, or `VOLUME` — to choose the light model. "
        "Attach a `Light` to a `Node` to position and orient it."
    ),
    "LightType": (
        "`LightType` is an enumeration of supported light source types: `POINT`, `DIRECTIONAL`, "
        "`SPOT`, `AREA`, and `VOLUME`. "
        "Assign one of these values to `Light.lightType` when constructing or configuring a light."
    ),
    "MappingMode": (
        "`MappingMode` specifies how vertex element data (normals, UVs, colours, etc.) is "
        "associated with geometry. "
        "Options are `CONTROL_POINT` (one value per vertex), `POLYGON_VERTEX` (one per polygon "
        "corner), `POLYGON` (one per face), `EDGE` (one per edge), and `ALL_SAME` (one for all)."
    ),
    "Material": (
        "`Material` is the abstract base class for all surface shading descriptions. "
        "It provides `getTexture` and `setTexture` methods for associating `TextureBase` objects "
        "with named slots (diffuse, specular, normal, etc.). "
        "Use concrete subclasses — `LambertMaterial`, `PhongMaterial`, or `PbrMaterial` — "
        "when assigning materials to nodes."
    ),
    "MathUtils": (
        "`MathUtils` is a static utility class for common 3D math operations. "
        "It provides degree/radian conversion, surface normal calculation, ray-triangle and "
        "ray-plane intersection tests, point-in-triangle testing, and a numeric clamp helper. "
        "All methods are static and operate on `Vector3` or scalar values."
    ),
    "Matrix4": (
        "`Matrix4` is a 4×4 double-precision matrix for 3D transform and projection calculations. "
        "It supports construction from TRS components or raw element values, concatenation, "
        "transposition, normalisation, inversion, decomposition, and conversion to a flat array. "
        "Factory methods cover identity, translation, scale, Euler rotation, and quaternion "
        "rotation matrices."
    ),
    "Mesh": (
        "`Mesh` is the primary polygon geometry type in Aspose.3D. "
        "It extends `Geometry` with a polygon list (`polygons`), edge connectivity (`edges`), "
        "and deformer support. "
        "Use `createPolygon` to build faces, `triangulate` to convert to triangle-only topology, "
        "`optimize` to weld vertices, and `doBoolean` for CSG union/subtraction/intersection."
    ),
    "Node": (
        "`Node` is the fundamental building block of the Aspose.3D scene graph. "
        "Each node has a local `transform`, an optional `entity` (mesh, light, camera, etc.), "
        "a list of `materials`, and child and parent node references that form a tree rooted at "
        "`Scene.rootNode`. "
        "Create children with `createChildNode` and evaluate world-space transforms with "
        "`evaluateGlobalTransform`."
    ),
    "ObjExporter": (
        "`ObjExporter` writes a `Scene` to the Wavefront OBJ format. "
        "It is registered via `ObjPlugin` and called automatically by `Scene.save` for OBJ targets. "
        "Use `ObjSaveOptions` to control coordinate flipping, material export, and scale."
    ),
    "ObjFormat": (
        "`ObjFormat` is the `FileFormat` descriptor for the Wavefront OBJ format. "
        "It reports extension, MIME type, and import/export capabilities, and provides factory "
        "methods for `ObjLoadOptions` and `ObjSaveOptions`. "
        "Obtain the singleton with `ObjFormat.getInstance()`."
    ),
    "ObjFormatDetector": (
        "`ObjFormatDetector` inspects a stream or file name to identify Wavefront OBJ content. "
        "It is registered in `IOService` and invoked automatically during scene loading."
    ),
    "ObjImporter": (
        "`ObjImporter` reads a Wavefront OBJ file into a `Scene`. "
        "It is invoked automatically by `Scene.open` when an OBJ file is detected. "
        "Pass an `ObjLoadOptions` instance to configure coordinate-system handling, scale, "
        "and normal normalization."
    ),
    "ObjLoadOptions": (
        "`ObjLoadOptions` configures OBJ import behaviour. "
        "Key settings are `flipCoordinateSystem`, `enableMaterials` (load the associated .mtl "
        "file), `scale` (uniform scale factor), and `normalizeNormal`."
    ),
    "ObjPlugin": (
        "`ObjPlugin` registers all Wavefront OBJ I/O components with the `IOService`. "
        "Obtain the singleton with `ObjPlugin.getInstance()`; it is registered automatically "
        "when the package loads."
    ),
    "ObjSaveOptions": (
        "`ObjSaveOptions` controls OBJ export settings. "
        "Options include `applyUnitScale`, `pointCloud` (export as points only), `verbose` "
        "logging, `serializeW` (include W in normals), `enableMaterials`, `flipCoordinateSystem`, "
        "and an `axisSystem` remapping."
    ),
    "ParseException": (
        "`ParseException` is thrown when the FBX text or binary parser encounters malformed "
        "or unexpected input. "
        "It extends the built-in JavaScript `Error` class and includes a descriptive `msg`."
    ),
    "PbrMaterial": (
        "`PbrMaterial` implements a physically based rendering (PBR) metallic-roughness material. "
        "It exposes `albedo` colour, metallic and roughness factors, and texture slots for "
        "albedo, normal, metallic-roughness, occlusion, and emissive maps. "
        "Use `PbrMaterial.fromMaterial` to convert a legacy `Material` to PBR."
    ),
    "PhongMaterial": (
        "`PhongMaterial` extends `LambertMaterial` with specular highlights. "
        "It adds `specularColor`, `specularFactor`, `shininess`, and reflection properties, "
        "implementing the classic Phong shading model used widely in FBX and COLLADA files."
    ),
    "PolygonModifier": (
        "`PolygonModifier` provides static geometry processing operations. "
        "The `triangulate` method converts a mesh, node, or entire scene's polygon geometry "
        "to triangles, which is required for many rendering and export pipelines."
    ),
    "ProjectionType": (
        "`ProjectionType` is an enumeration of camera projection modes. "
        "Use `PERSPECTIVE` for standard 3D projection with foreshortening, or `ORTHOGRAPHIC` "
        "for parallel projection without depth distortion."
    ),
    "Property": (
        "`Property` stores a single named value in an `A3DObject`'s property bag. "
        "It holds a `name`, a typed `value`, and a `valueType` descriptor. "
        "Extra metadata can be attached with `getExtra`/`setExtra`. "
        "Enumerate properties through `A3DObject.properties`."
    ),
    "PropertyCollection": (
        "`PropertyCollection` is the ordered container of `Property` objects attached to an "
        "`A3DObject`. "
        "It supports lookup by name with `findProperty`, indexed access with `getItem`, "
        "removal, and iteration via the standard JavaScript iterator protocol."
    ),
    "Quaternion": (
        "`Quaternion` represents an orientation as a unit quaternion with `w`, `x`, `y`, `z` "
        "components. "
        "It supports normalisation, conjugate, inverse, dot product, concatenation, conversion "
        "to/from Euler angles and angle-axis form, spherical linear interpolation (SLERP), "
        "and conversion to a `Matrix4`."
    ),
    "Rect": (
        "`Rect` represents an integer or floating-point rectangle defined by `x`, `y`, `width`, "
        "and `height`. "
        "It exposes `left`, `right`, `top`, and `bottom` convenience accessors and a "
        "`contains(x, y)` hit test."
    ),
    "ReferenceMode": (
        "`ReferenceMode` specifies how a vertex element's data array is indexed. "
        "`DIRECT` means each data entry corresponds directly to the mapping index, "
        "`INDEX` provides an explicit index array, and `INDEX_TO_DIRECT` combines both."
    ),
    "RelativeRectangle": (
        "`RelativeRectangle` describes a rectangle using scale factors and pixel offsets relative "
        "to a parent rectangle. "
        "Call `toAbsolute` to resolve it to a concrete `Rect` given the parent dimensions, "
        "or use `fromScale` to construct one from pure scale values."
    ),
    "RotationMode": (
        "`RotationMode` is an enumeration for camera rotation behaviour. "
        "`FIXED` locks the camera direction, while `ORBIT` allows the camera to rotate "
        "around its `target` point."
    ),
    "RotationOrder": (
        "`RotationOrder` specifies the order in which Euler angle rotations are applied: "
        "`XYZ`, `XZY`, `YZX`, `YXZ`, `ZXY`, or `ZYX`. "
        "Set this on a node's transform to match the convention used by the source file format."
    ),
    "Scene": (
        "`Scene` is the top-level container for a 3D document in Aspose.3D. "
        "It owns the scene graph through `rootNode`, stores animation clips, sub-scenes, a "
        "custom-object library, and asset metadata. "
        "Load files with `Scene.open` or `Scene.fromFile`, and write them with `Scene.save` "
        "or `Scene.saveToBuffer`."
    ),
    "SceneObject": (
        "`SceneObject` is the base class for any object that belongs to a `Scene`. "
        "It extends `A3DObject` with a back-reference to its owning `Scene`, accessible through "
        "the `scene` property."
    ),
    "SemanticAttribute": (
        "`SemanticAttribute` pairs a `VertexFieldSemantic` enumeration value with an optional "
        "string alias, used to declare the intended use of a vertex data field in a "
        "`VertexDeclaration`. "
        "For example, a field with semantic `POSITION` describes vertex positions."
    ),
    "SplitMeshPolicy": (
        "`SplitMeshPolicy` controls how vertex element data is handled when a mesh is split "
        "by material. "
        "`ADJUST` reindexes existing data, while `CLONE_DATA` duplicates vertex data "
        "for each sub-mesh."
    ),
    "StepMode": (
        "`StepMode` is an enumeration that controls which adjacent keyframe value is used "
        "for a `CONSTANT`-interpolation keyframe: `PREVIOUS_VALUE` holds the current key's "
        "value until the next key, while `NEXT_VALUE` jumps immediately to the next key's value."
    ),
    "StlExporter": (
        "`StlExporter` writes a `Scene` to the STL (stereolithography) format. "
        "It is registered via `StlPlugin` and invoked by `Scene.save` for STL targets. "
        "Use `StlSaveOptions` to choose between ASCII and binary output and to set scale "
        "and coordinate-system options."
    ),
    "StlFormat": (
        "`StlFormat` is the `FileFormat` descriptor for the STL stereolithography format. "
        "It reports the extension, content type, and import/export support, and provides factory "
        "methods for `StlLoadOptions` and `StlSaveOptions`. "
        "Obtain the singleton with `StlFormat.getInstance()`."
    ),
    "StlFormatDetector": (
        "`StlFormatDetector` identifies whether an input stream or file name is in STL format. "
        "It is registered in `IOService` and invoked automatically during scene loading."
    ),
    "StlImporter": (
        "`StlImporter` reads an STL file (ASCII or binary) into a `Scene`. "
        "It is invoked automatically by `Scene.open` when an STL file is detected. "
        "Pass an `StlLoadOptions` to configure coordinate flipping and scale."
    ),
    "StlLoadOptions": (
        "`StlLoadOptions` configures STL import behaviour. "
        "Set `flipCoordinateSystem` to adjust axis conventions, and `scale` to apply a uniform "
        "scale factor to all imported geometry."
    ),
    "StlPlugin": (
        "`StlPlugin` registers all STL I/O components with the `IOService`. "
        "Obtain the singleton with `StlPlugin.getInstance()`; registration is automatic "
        "when the package loads."
    ),
    "StlSaveOptions": (
        "`StlSaveOptions` controls STL export settings. "
        "Set `binaryMode` to `true` for compact binary STL output, or `false` for human-readable "
        "ASCII. "
        "The `flipCoordinateSystem` and `scale` options mirror those on `StlLoadOptions`."
    ),
    "TextureBase": (
        "`TextureBase` is the abstract base class for texture objects in Aspose.3D. "
        "It holds raw `content` data (image bytes or a reference) and provides the common "
        "interface used by `Material.setTexture` and `Material.getTexture`. "
        "Concrete subclasses add format-specific behaviour."
    ),
    "TextureMapping": (
        "`TextureMapping` is an enumeration of standard texture usage slots: `AMBIENT`, "
        "`EMISSIVE`, `DIFFUSE`, `OPACITY`, `BUMP`, `NORMAL`, `SPECULAR`, `GLOW`, "
        "`REFLECTION`, `SHADOW`, `SHININESS`, and `DISPLACEMENT`. "
        "Pass a `TextureMapping` value to `Geometry.createElementUV` to specify the UV set's purpose."
    ),
    "ThreeMfExporter": (
        "`ThreeMfExporter` writes a `Scene` to the 3MF (3D Manufacturing Format) format. "
        "It is registered via `ThreeMfPlugin` and invoked by `Scene.save` for 3MF targets. "
        "Use `ThreeMfSaveOptions` to control compression, build list, units, and pretty-printing."
    ),
    "ThreeMfFormat": (
        "`ThreeMfFormat` is the `FileFormat` descriptor for the 3MF manufacturing format. "
        "In addition to the standard format descriptor API, it provides helpers for marking "
        "nodes as buildable, getting and setting build transforms, and assigning 3MF object types. "
        "Obtain the singleton with `ThreeMfFormat.getInstance()`."
    ),
    "ThreeMfFormatDetector": (
        "`ThreeMfFormatDetector` identifies whether an input stream or file name is in 3MF format. "
        "It is registered in `IOService` and invoked automatically during scene loading."
    ),
    "ThreeMfImporter": (
        "`ThreeMfImporter` reads a 3MF file into a `Scene`. "
        "It is invoked automatically by `Scene.open` when a 3MF file is detected. "
        "Pass a `ThreeMfLoadOptions` instance to configure coordinate-system conventions."
    ),
    "ThreeMfLoadOptions": (
        "`ThreeMfLoadOptions` configures 3MF import behaviour. "
        "Set `flipCoordinateSystem` to convert from the 3MF right-handed Y-up convention to "
        "the coordinate system used by your application."
    ),
    "ThreeMfPlugin": (
        "`ThreeMfPlugin` registers all 3MF I/O components with the `IOService`. "
        "Obtain the singleton with `ThreeMfPlugin.getInstance()`; registration is automatic "
        "when the package loads."
    ),
    "ThreeMfSaveOptions": (
        "`ThreeMfSaveOptions` controls 3MF export settings. "
        "Options include `enableCompression` (ZIP compression of the package), `buildAll` "
        "(include all scene nodes in the build list), `flipCoordinateSystem`, `unit` (length "
        "unit string, e.g. millimeter), and `prettyPrint` (human-readable XML)."
    ),
    "Transform": (
        "`Transform` stores the local position, orientation, and scale of a `Node` in the scene "
        "graph. "
        "It exposes `translation`, `scaling`, `rotation` (quaternion), `eulerAngles`, and pivot "
        "offsets for pre- and post-rotation. "
        "Fluent setter methods (`setTranslation`, `setScale`, `setEulerAngles`, etc.) return the "
        "`Transform` instance for chaining. "
        "Access via `Node.transform`."
    ),
    "TransformBuilder": (
        "`TransformBuilder` assembles a composite `Matrix4` transform through a fluent API. "
        "Chain calls to `translate`, `scale`, `rotateRadian`, `rotateDegree`, `rotateEulerRadian`, "
        "and `rotate` to build the matrix incrementally. "
        "The `composeOrder` property controls whether each operation is appended or prepended."
    ),
    "Vector2": (
        "`Vector2` is a double-precision 2D vector with `x` and `y` components. "
        "It provides `set`, indexed access, string formatting, equality testing, and static "
        "`parse` for deserialising from a string. "
        "`length` and `length2` give the Euclidean length and its square."
    ),
    "Vector3": (
        "`Vector3` is a double-precision 3D vector with `x`, `y`, and `z` components. "
        "It provides dot product, cross product, normalisation, angle calculation, component-wise "
        "sine and cosine, comparison, arithmetic helpers (`minus`, `times`), and static factories "
        "for zero, one, and unit-axis vectors."
    ),
    "Vector4": (
        "`Vector4` is a double-precision 4D vector with `x`, `y`, `z`, and `w` components. "
        "It supports indexed access, string formatting, and equality comparison. "
        "Use it for homogeneous coordinates and colour values that require double precision."
    ),
    "Vertex": (
        "`Vertex` provides typed read access to a single vertex within a `TriMesh` vertex buffer. "
        "Use the `readVector4`, `readVector3`, `readVector2`, `readFloat`, `readDouble`, "
        "and their `FVector` variants to extract typed field values identified by `VertexField`."
    ),
    "VertexDeclaration": (
        "`VertexDeclaration` describes the layout of a vertex buffer by listing the `VertexField` "
        "entries that compose each vertex record. "
        "Add fields with `addField`, specify their data type, semantic, index, and alias, "
        "then seal the declaration before creating a buffer."
    ),
    "VertexElement": (
        "`VertexElement` is the base class for all per-vertex data channels attached to a "
        "`Geometry`. "
        "Each element has a `mappingMode` (how data maps to geometry) and a `referenceMode` "
        "(direct or indexed). "
        "Concrete subclasses store typed data arrays: `VertexElementNormal`, `VertexElementUV`, "
        "`VertexElementVertexColor`, etc."
    ),
    "VertexElementBinormal": (
        "`VertexElementBinormal` stores per-vertex binormal vectors on a `Geometry`. "
        "Binormals are used with normals and tangents to define a tangent space for normal mapping. "
        "Add one to a geometry with `Geometry.createElement(VertexElementType.BINORMAL, ...)`."
    ),
    "VertexElementFVector": (
        "`VertexElementFVector` is the base class for vertex elements that store `FVector4` "
        "single-precision data. "
        "It provides `setData`, `setIndices`, `clear`, and `copyTo` methods and exposes `data` "
        "and `indices` arrays. "
        "Subclasses include `VertexElementNormal`, `VertexElementTangent`, `VertexElementUV`, "
        "and `VertexElementVertexColor`."
    ),
    "VertexElementIntsTemplate": (
        "`VertexElementIntsTemplate` is the base class for vertex elements that store integer "
        "arrays. "
        "It provides `setData`, `setIndices`, `clear`, and `copyTo` helpers for integer-typed "
        "per-vertex data. "
        "`VertexElementSmoothingGroup` extends this class."
    ),
    "VertexElementNormal": (
        "`VertexElementNormal` stores per-vertex or per-polygon-vertex surface normal vectors on "
        "a `Geometry`. "
        "Normals are required for lighting calculations and are typically set using "
        "`Geometry.createElement(VertexElementType.NORMAL, mappingMode, referenceMode)`."
    ),
    "VertexElementSmoothingGroup": (
        "`VertexElementSmoothingGroup` stores integer smoothing group IDs per polygon on a "
        "`Geometry`. "
        "Faces sharing the same smoothing group ID will have their normals averaged across "
        "the shared edge, producing a smooth appearance."
    ),
    "VertexElementTangent": (
        "`VertexElementTangent` stores per-vertex tangent vectors on a `Geometry`. "
        "Tangents, together with binormals and normals, define the tangent-space basis used "
        "for normal map decoding in shaders."
    ),
    "VertexElementType": (
        "`VertexElementType` is an enumeration of the standard vertex data channel types. "
        "Use these values when calling `Geometry.createElement` or `getElement` to identify "
        "channels such as `NORMAL`, `UV`, `TANGENT`, `VERTEX_COLOR`, `SMOOTHING_GROUP`, and more."
    ),
    "VertexElementUV": (
        "`VertexElementUV` stores per-vertex UV texture coordinates on a `Geometry`. "
        "The `textureMapping` property identifies the texture slot (diffuse, normal, etc.) "
        "this UV set corresponds to. "
        "Access UV data as `FVector4` via `data` or as `FVector2` via `uvData`."
    ),
    "VertexElementVertexColor": (
        "`VertexElementVertexColor` stores per-vertex or per-polygon-vertex RGBA colour values "
        "on a `Geometry`. "
        "Add one with `Geometry.createElement(VertexElementType.VERTEX_COLOR, ...)` to bake "
        "vertex colours into the mesh."
    ),
    "VertexField": (
        "`VertexField` describes one typed attribute within a `VertexDeclaration` — its data "
        "type, semantic, alias, byte offset within the vertex record, and multi-channel index. "
        "Fields are created by `VertexDeclaration.addField` and passed to `Vertex.read*` methods "
        "to extract data from a vertex buffer."
    ),
    "VertexFieldDataType": (
        "`VertexFieldDataType` is an enumeration of the scalar and vector data types that can "
        "occupy a `VertexField` — for example, `VECTOR2`, `VECTOR3`, `VECTOR4`, `F_VECTOR2`, "
        "`F_VECTOR3`, and `F_VECTOR4` for double and single precision variants."
    ),
    "VertexFieldSemantic": (
        "`VertexFieldSemantic` is an enumeration that identifies the intended use of a "
        "`VertexField`. "
        "Values include `POSITION`, `NORMAL`, `TANGENT`, `BINORMAL`, `UV`, `COLOR`, `WEIGHT`, "
        "and others, enabling the runtime and shaders to locate specific attributes by role."
    ),
    "Watermark": (
        "`Watermark` provides utilities for embedding and decoding invisible text watermarks in "
        "a `Mesh`. "
        "Use it to protect ownership of 3D assets by hiding an encoded string in the geometry "
        "vertex data."
    ),
    "WeightedMode": (
        "`WeightedMode` is an enumeration that controls whether keyframe tangent weights are "
        "treated as normalized (`NONE`) or as explicit time-weighted values "
        "(`RIGHT`, `NEXT_LEFT`, or `BOTH`) for Bezier interpolation."
    ),
}

# -----------------------------------------------------------------------
# Method/property descriptions grounded in signature semantics.
# -----------------------------------------------------------------------
MEMBER_DESCRIPTIONS = {
    # A3DObject
    "findProperty(propertyName: string)": "Searches the property collection for a property with the given name and returns it, or null if not found.",
    "getProperty(property: string)": "Returns the current value of the named property.",
    "setProperty(property: string, value: any)": "Sets the value of the named property, creating it if it does not already exist.",
    "removeProperty(property: string | Property)": "Removes the specified property from the collection and returns true if it was present.",
    # Scene
    "clear()": "Removes all content from the scene, resetting it to an empty state.",
    "createAnimationClip(name: string)": "Creates and registers a new named animation clip in the scene.",
    "getAnimationClip(name: string)": "Returns the animation clip with the given name, or null if none exists.",
    "open(fileOrStream: any, options: any)": "Loads 3D content from a file path or stream, populating this scene with the parsed data.",
    "openFromBuffer(buffer: Buffer | Uint8Array, options: any)": "Loads 3D content from an in-memory byte buffer, populating this scene with the parsed data.",
    "save(fileOrStream: any, formatOrOptions: any, options: any)": "Writes this scene to a file path or stream using the specified format or save options.",
    "saveToBuffer(format: string, _options: any)": "Serialises this scene to a Buffer in the specified format and returns the result.",
    "render(_camera: any, _file_name_or_bitmap: any, _size: any, _format: any, _options: any)": "Renders a still image of the scene from the given camera viewpoint to a file or bitmap.",
    "fromFile(fileName: string)": "Static factory: opens the specified file and returns a populated Scene instance.",
    # Scene properties
    "VERSION": "The library version string for the @aspose/3d package.",
    "rootNode": "The root node of the scene graph; all scene-object nodes descend from this node.",
    "subScenes": "Additional child scenes embedded within this document (e.g., multiple takes).",
    "library": "A collection of custom objects stored in the scene library, not directly in the scene graph.",
    "assetInfo": "Document-level metadata such as creator, dates, and unit information.",
    "animationClips": "All animation clips registered in this scene.",
    "currentAnimationClip": "The animation clip currently selected for playback; may be null.",
    "poses": "Pose objects stored in the scene, used for bind-pose and other static reference poses.",
    # Node methods
    "addEntity(entity: Entity)": "Attaches an entity (mesh, light, camera, etc.) to this node.",
    "removeEntity(entity: Entity)": "Detaches the specified entity from this node.",
    "clearEntities()": "Removes all attached entities from this node.",
    "addChildNode(node: Node)": "Appends an existing node as a child of this node.",
    "createChildNode(nodeName: string, entity: Entity, material: Material)": "Creates a new named child node with an optional entity and material already attached.",
    "getChild(indexOrName: number | string)": "Returns the child node at the given index or with the given name, or null if not found.",
    "merge(node: Node)": "Merges all children and entities from the given node into this node.",
    "evaluateGlobalTransform(withGeometricTransform: boolean)": "Computes and returns the accumulated world-space transform matrix for this node.",
    "getBoundingBox()": "Computes and returns the axis-aligned bounding box enclosing this node and all its descendants.",
    "selectSingleObject(_path: string)": "Evaluates a path expression against the scene graph and returns the first matching object.",
    "selectObjects(_path: string)": "Evaluates a path expression against the scene graph and returns all matching objects.",
    # Node properties
    "parentNode": "The parent node in the scene graph hierarchy, or null for the root node.",
    "childNodes": "An array of all direct child nodes.",
    "entities": "All entities attached to this node.",
    "entity": "The primary entity attached to this node, or undefined if none.",
    "materials": "The list of materials assigned to this node.",
    "material": "The primary material assigned to this node, or null if none.",
    "transform": "The local transform (position, rotation, scale) of this node.",
    "globalTransform": "The computed world-space transform of this node.",
    "visible": "Whether this node is visible during rendering.",
    "excluded": "When true, excludes this node from rendering and bounding-box calculations.",
    "metaDatas": "Application-defined metadata objects attached to this node.",
    # Mesh methods
    "createPolygon()": "Appends a new polygon to the mesh using the currently accumulated control point indices.",
    "getPolygonSize(index: number)": "Returns the number of vertices in the polygon at the specified index.",
    "toMesh()": "Returns this mesh object (identity operation; satisfies the geometry conversion interface).",
    "optimize(_vertexElements: boolean, _toleranceControlPoint: number, _toleranceNormal: number, _toleranceUV: number)": "Welds duplicate vertices within the given tolerances and returns the optimised mesh.",
    "doBoolean(_op: any, _a: Mesh, _transformA: any, _b: Mesh, _transformB: any)": "Performs a CSG boolean operation (union, subtraction, or intersection) on two meshes and returns the result.",
    "isManifold()": "Returns true if the mesh surface is manifold (every edge is shared by exactly two faces).",
    "union(_a: Mesh, _b: Mesh)": "Returns the CSG union of two meshes.",
    "difference(_a: Mesh, _b: Mesh)": "Returns the CSG subtraction of mesh _b from mesh _a.",
    "intersect(_a: Mesh, _b: Mesh)": "Returns the CSG intersection of two meshes.",
    "triangulate()": "Converts all polygons in the mesh to triangles and returns the triangulated mesh.",
    "getEntityRendererKey()": "Returns an internal renderer key used to identify the entity type during rendering.",
    # Mesh properties
    "edges": "The edge list as pairs of vertex indices.",
    "polygonCount": "The total number of polygons in the mesh.",
    "polygons": "The polygon definitions as an array of vertex-index arrays.",
    "deformers": "Deformer objects (e.g., skinning deformers) applied to this mesh.",
    # FbxExporter methods
    "supportsFormat(fileFormat: FileFormat)": "Returns true if this exporter can write the specified file format.",
    "export(scene: Scene, stream: any, _options: SaveOptions)": "Serialises the given scene to the output stream in this exporter's format.",
    # FbxExporter properties
    "meshes": "The mesh objects collected from the scene during export.",
    "nodes": "The scene nodes collected from the scene during export.",
    # Geometry methods
    "addControlPoint(point)": "Appends a new control point (vertex position) to the geometry's vertex list.",
    "createElement(elementType, mappingMode, referenceMode)": "Creates and attaches a new typed vertex element channel to this geometry.",
    "createElementUV(uvMapping, mappingMode, referenceMode)": "Creates and attaches a new UV vertex element for the specified texture mapping slot.",
    "addElement(element)": "Adds an already-constructed vertex element to this geometry.",
    "getElement(elementType)": "Returns the first vertex element of the specified type, or null if none exists.",
    "getVertexElementOfUV(textureMapping)": "Returns the UV vertex element associated with the specified texture mapping slot, or null.",
    # Geometry properties
    "castShadows": "Whether this geometry casts shadows in shadow-enabled renders.",
    "receiveShadows": "Whether this geometry receives shadows cast by other objects.",
    "vertexElements": "All vertex element channels (normals, UVs, colours, etc.) attached to this geometry.",
    "controlPoints": "The vertex positions as an array of Vector4 values.",
    # Transform methods
    "setTranslation(tx, ty, tz)": "Sets the local translation of this node and returns the Transform for chaining.",
    "setScale(sx, sy, sz)": "Sets the local uniform scale of this node and returns the Transform for chaining.",
    "setEulerAngles(rx, ry, rz)": "Sets the local rotation from Euler angles (degrees) and returns the Transform for chaining.",
    "setRotation(rw, rx, ry, rz)": "Sets the local rotation from a quaternion and returns the Transform for chaining.",
    "setPreRotation(rx, ry, rz)": "Sets the pre-rotation offset applied before the main rotation.",
    "setPostRotation(rx, ry, rz)": "Sets the post-rotation offset applied after the main rotation.",
    "setGeometricTranslation(x, y, z)": "Sets a geometric translation that offsets geometry without affecting child-node transforms.",
    "setGeometricScaling(sx, sy, sz)": "Sets a geometric scale that resizes geometry without affecting child-node transforms.",
    "setGeometricRotation(rx, ry, rz)": "Sets a geometric rotation that rotates geometry without affecting child-node transforms.",
    # Transform properties
    "translation": "The local translation vector (position offset from parent).",
    "scaling": "The local scale vector.",
    "rotation": "The local rotation as a Quaternion.",
    "eulerAngles": "The local rotation expressed as Euler angles in degrees.",
    "scalingOffset": "The offset applied to the scaling pivot point.",
    "scalingPivot": "The pivot point around which scaling is applied.",
    "rotationOffset": "The offset applied to the rotation pivot point.",
    "rotationPivot": "The pivot point around which rotation is applied.",
    "preRotation": "A fixed pre-rotation applied before the animated rotation.",
    "postRotation": "A fixed post-rotation applied after the animated rotation.",
    "geometricTranslation": "A translation applied to geometry only, not propagated to child nodes.",
    "geometricScaling": "A scale applied to geometry only, not propagated to child nodes.",
    "geometricRotation": "A rotation applied to geometry only, not propagated to child nodes.",
    "transformMatrix": "The full composed local transform as a Matrix4.",
    # GlobalTransform properties
    "eulerAngles": "World-space Euler angles derived from the global rotation quaternion.",
    # Material methods
    "getTexture(_slotName)": "Returns the texture assigned to the named slot, or null if none is set.",
    "setTexture(_slotName, _texture)": "Assigns a texture to the named slot (e.g., MAP_DIFFUSE, MAP_NORMAL).",
    # LambertMaterial properties
    "MAP_SPECULAR": "Slot name constant for the specular texture channel.",
    "MAP_DIFFUSE": "Slot name constant for the diffuse colour texture channel.",
    "MAP_EMISSIVE": "Slot name constant for the emissive texture channel.",
    "MAP_AMBIENT": "Slot name constant for the ambient texture channel.",
    "MAP_NORMAL": "Slot name constant for the normal map texture channel.",
    "emissiveColor": "The self-illumination colour of the material.",
    "ambientColor": "The ambient reflectance colour of the material.",
    "diffuseColor": "The primary diffuse reflectance colour of the material.",
    "transparentColor": "The transparency colour (used for chromatic transparency).",
    "transparency": "The overall transparency factor from 0 (opaque) to 1 (fully transparent).",
    # PhongMaterial properties
    "specularColor": "The specular highlight colour of the material.",
    "specularFactor": "A scalar multiplier for the specular colour contribution.",
    "shininess": "The Phong shininess exponent controlling the size of specular highlights.",
    "reflectionColor": "The reflection colour used for environment reflections.",
    "reflectionFactor": "A scalar multiplier for the reflection colour contribution.",
    # PbrMaterial properties
    "albedo": "The base colour (albedo) of the PBR material as a Vector3 RGB value.",
    "albedoTexture": "A texture that multiplies the albedo colour.",
    "normalTexture": "A normal map texture for surface detail.",
    "metallicFactor": "The metallic factor from 0 (dielectric) to 1 (fully metallic).",
    "roughnessFactor": "The roughness factor from 0 (smooth) to 1 (fully rough).",
    "metallicRoughness": "A combined metallic-roughness texture (B channel = metallic, G = roughness).",
    "occlusionTexture": "An ambient occlusion texture (R channel) that darkens indirect lighting.",
    "occlusionFactor": "A scalar multiplier for the occlusion texture strength.",
    "emissiveTexture": "A texture for self-illumination, multiplied by the emissive colour.",
    "emissiveColor": "The emissive (self-illumination) colour of the PBR material.",
    # Camera properties
    "nearPlane": "The distance to the near clipping plane; geometry closer than this is not rendered.",
    "farPlane": "The distance to the far clipping plane; geometry beyond this is not rendered.",
    "aspect": "The camera's aspect ratio (width divided by height).",
    "orthoHeight": "The height of the orthographic view volume in world units.",
    "up": "The up vector that defines the camera's vertical orientation.",
    "lookAt": "The world-space point the camera is aimed at.",
    "direction": "The view direction vector of the camera.",
    "target": "A node that the camera tracks; when set, the camera always faces this node.",
    "apertureMode": "Controls how fieldOfView is derived from the camera's aperture dimensions.",
    "fieldOfView": "The diagonal field of view angle in degrees for perspective projection.",
    "fieldOfViewX": "The horizontal field of view angle in degrees.",
    "fieldOfViewY": "The vertical field of view angle in degrees.",
    "width": "The aperture width used when apertureMode is HORZ_AND_VERT.",
    "height": "The aperture height used when apertureMode is HORZ_AND_VERT.",
    "aspectRatio": "The computed aspect ratio derived from the aperture dimensions.",
    "magnification": "The magnification factor for orthographic projection.",
    "projectionType": "The projection type: PERSPECTIVE or ORTHOGRAPHIC.",
    # AnimationClip properties
    "description": "A human-readable description of the animation clip.",
    "start": "The start time of the animation clip in seconds.",
    "stop": "The stop time of the animation clip in seconds.",
    "animations": "The animation nodes that drive scene-object properties within this clip.",
    # AnimationNode methods
    "findBindPoint(_target, name)": "Searches for a bind point on the target object with the given property name; returns null if not found.",
    "getBindPoint(target, propName, create)": "Returns the bind point for the named property on the target, optionally creating it.",
    "createBindPoint(obj, propName)": "Creates and returns a new bind point connecting the named property of the target object.",
    "getKeyframeSequence(target, propName, channelName, create)": "Retrieves or optionally creates the keyframe sequence for the specified property channel.",
    # AnimationNode properties
    "bindPoints": "The list of bind points connecting scene-object properties to animation curves.",
    "subAnimations": "Nested animation nodes for hierarchical animation rigs.",
    # BindPoint methods
    "addChannel(name, value, _type)": "Adds an animation channel with the given name and default value; returns true if the channel was newly created.",
    "getKeyframeSequence(channelName)": "Returns the keyframe sequence for the named channel, or null if none exists.",
    "createKeyframeSequence(name)": "Creates and returns a new keyframe sequence for the named channel.",
    "bindKeyframeSequence(channelName, sequence)": "Associates an existing keyframe sequence with the named animation channel.",
    "getChannel(channelName)": "Returns the animation channel with the given name, or null.",
    "resetChannels()": "Removes all animation channels from this bind point.",
    # BindPoint properties
    "property": "The scene-object property this bind point animates.",
    "channelsCount": "The number of animation channels registered on this bind point.",
    "scene": "The scene that owns this bind point.",
    # KeyFrame properties
    "time": "The time position of this keyframe in seconds.",
    "value": "The scalar value at this keyframe.",
    "interpolation": "The interpolation method used between this keyframe and the next.",
    "tangentWeightMode": "Controls whether tangent weights are normalised or time-weighted.",
    "stepMode": "For CONSTANT interpolation, controls whether the current or next value is used.",
    "nextInTangent": "The incoming tangent vector at the next keyframe (for Bezier interpolation).",
    "outTangent": "The outgoing tangent vector at this keyframe (for Bezier interpolation).",
    "outWeight": "The weight of the outgoing tangent for weighted Bezier interpolation.",
    "nextInWeight": "The weight of the incoming tangent at the next keyframe.",
    "tension": "The tension parameter for TCB spline interpolation.",
    "continuity": "The continuity parameter for TCB spline interpolation.",
    "bias": "The bias parameter for TCB spline interpolation.",
    "independentTangent": "When true, incoming and outgoing tangents are controlled independently.",
    "flat": "When true, the tangent is forced horizontal (zero slope).",
    "timeIndependentTangent": "When true, the tangent direction is not affected by time scaling.",
    "curve": "The parent keyframe sequence this keyframe belongs to.",
    # KeyframeSequence methods
    "reset()": "Removes all keyframes from this sequence.",
    "add(time, value, interpolation)": "Appends a new keyframe at the given time with the specified value and interpolation mode.",
    "setBindPoint(value)": "Sets the bind point that owns this keyframe sequence.",
    # KeyframeSequence properties
    "bindPoint": "The bind point that this keyframe sequence is attached to.",
    "keyFrames": "The sorted list of keyframes in this animation curve.",
    "postBehavior": "The extrapolation behaviour applied after the last keyframe.",
    "preBehavior": "The extrapolation behaviour applied before the first keyframe.",
    # BoundingBox methods
    "null()": "Returns a null (empty) bounding box with no defined extents.",
    "infinite()": "Returns a bounding box representing infinite extent in all directions.",
    "merge()": "Expands this bounding box to include the given point or box.",
    "contains(arg)": "Returns true if the given point or bounding box lies within this bounding box.",
    "overlapsWith(box)": "Returns true if this bounding box overlaps with the given box.",
    "scale()": "Returns a scalar representing the approximate size of the bounding box.",
    # BoundingBox properties
    "minimum": "The minimum corner of the bounding box.",
    "maximum": "The maximum corner of the bounding box.",
    "center": "The geometric centre of the bounding box.",
    "size": "The dimensions (width, height, depth) of the bounding box.",
    "extent": "The extent state of the bounding box (null, finite, or infinite).",
    # IOConfig properties
    "fileFormat": "The file format to use for this I/O operation; null means auto-detect.",
    "encoding": "The text encoding (e.g., UTF-8) used when reading or writing text-based formats.",
    "fileSystem": "The file system abstraction used to resolve external references such as textures.",
    "lookupPaths": "Additional search paths used when resolving relative file references.",
    "fileName": "The file name associated with this I/O operation, used for format detection and relative path resolution.",
    # IOService methods
    "instance()": "Returns the singleton IOService instance.",
    "registerExporter(exporter)": "Registers a custom exporter with the I/O service.",
    "registerImporter(importer)": "Registers a custom importer with the I/O service.",
    "registerDetector(detector)": "Registers a custom format detector with the I/O service.",
    "registerPlugin(plugin)": "Registers all components of a format plugin (importer, exporter, detector) in one call.",
    "detectFormat(stream, fileName)": "Inspects the stream and file name to determine the file format; returns null if unknown.",
    "createExporter(formatType)": "Creates and returns an exporter for the specified file format.",
    "createImporter(formatType)": "Creates and returns an importer for the specified file format.",
    "getPluginForFormat(fileFormat)": "Returns the plugin that handles the specified file format, or null.",
    "getPluginForExtension(extension)": "Returns the plugin associated with the given file extension, or null.",
    "getAllPlugins()": "Returns all registered format plugins.",
    # Property methods
    "getExtra(name)": "Returns the extra metadata value associated with the given name on this property.",
    "setExtra(name, value)": "Associates a metadata value with the given name on this property.",
    # PropertyCollection methods
    "findProperty(propertyName)": "Searches the collection for a property with the given name and returns it, or null.",
    "get(property)": "Returns the current value of the named property.",
    "removeProperty(property)": "Removes the specified property from the collection.",
    "getItem(key)": "Returns the property at the specified index.",
    "[Symbol.iterator]()": "Returns an iterator over all properties in the collection.",
    # PropertyCollection properties
    "count": "The number of properties in this collection.",
    "length": "The number of properties in this collection (alias for count).",
    # Property properties
    "value": "The current value stored in this property.",
    "valueType": "The type descriptor for the property value.",
    # Matrix4 methods
    "getItem(key)": "Returns the matrix element at the given linear index (row-major order).",
    "setItem(key, value)": "Sets the matrix element at the given linear index.",
    "transpose()": "Returns the transpose of this matrix.",
    "concatenate(m2)": "Returns the product of this matrix and m2 (matrix multiplication).",
    "normalize()": "Normalises the rotation component of this matrix and returns the result.",
    "inverse()": "Returns the inverse of this matrix.",
    "decompose(translation, scaling, rotation)": "Decomposes this matrix into its translation, scaling, and rotation components.",
    "setTRS(translation, rotation, scale)": "Sets this matrix from translation, rotation quaternion, and scale vectors.",
    "toArray()": "Returns the matrix elements as a flat 16-element array in row-major order.",
    "identity()": "Returns the 4x4 identity matrix.",
    "translate(tx, ty, tz)": "Returns a translation matrix for the given x, y, z offsets.",
    "scale(sx, sy, sz)": "Returns a scaling matrix for the given x, y, z factors.",
    "rotateFromEuler(rx, ry, rz)": "Returns a rotation matrix constructed from Euler angles in radians.",
    "rotate(angle, axis)": "Returns a rotation matrix for the given angle (radians) around the given axis.",
    "equals(other)": "Returns true if all elements of this matrix equal those of the other matrix.",
    # Matrix4 properties
    "determinant": "The determinant of this matrix.",
    # Quaternion methods
    "normalize()": "Returns a unit quaternion in the same direction as this quaternion.",
    "conjugate()": "Returns the conjugate of this quaternion (negated vector part).",
    "inverse()": "Returns the multiplicative inverse of this quaternion.",
    "dot(q)": "Returns the dot product of this quaternion and q.",
    "concat(rhs)": "Returns the product of this quaternion and rhs (rotation composition).",
    "eulerAngles()": "Returns the rotation expressed as Euler angles (pitch, yaw, roll) in radians.",
    "fromEulerAngle(pitch, yaw, roll)": "Returns a quaternion constructed from the given Euler angles in radians.",
    "fromAngleAxis(a, axis)": "Returns a quaternion representing a rotation of angle radians around the given axis.",
    "fromRotation(orig, dest)": "Returns the quaternion that rotates the orig direction to the dest direction.",
    "interpolate(t, fromQ, toQ)": "Returns a linearly interpolated quaternion between fromQ and toQ at parameter t.",
    "slerp(t, v1, v2)": "Returns the spherical linear interpolation between v1 and v2 at parameter t.",
    "toMatrix()": "Returns the equivalent rotation Matrix4 for this quaternion.",
    # Quaternion properties
    "w": "The scalar (real) component of the quaternion.",
    "x": "The x component of the quaternion's vector part.",
    "y": "The y component of the quaternion's vector part.",
    "z": "The z component of the quaternion's vector part.",
    "length": "The magnitude (norm) of the quaternion.",
    # Vector3 methods
    "set(newX, newY, newZ)": "Sets all three components in place.",
    "dot(rhs)": "Returns the dot product of this vector and rhs.",
    "cross(rhs)": "Returns the cross product of this vector and rhs.",
    "normalize()": "Returns a unit vector in the same direction.",
    "angleBetween(dir, up)": "Returns the signed angle in radians from this vector to dir, measured around the up axis.",
    "sin()": "Returns a vector with component-wise sine applied.",
    "cos()": "Returns a vector with component-wise cosine applied.",
    "compareTo(other)": "Returns a negative, zero, or positive value for ordering purposes.",
    "parse(input)": "Parses a string representation and returns the corresponding vector.",
    "minus(v)": "Returns the result of subtracting v from this vector.",
    "times(scalar)": "Returns this vector scaled by the given scalar.",
    # Vector2 methods
    "set(newX, newY)": "Sets both components in place.",
    "getItem(key)": "Returns the component at index 0 (x) or 1 (y).",
    "setItem(key, value)": "Sets the component at the given index.",
    # Extrapolation properties
    "type": "The extrapolation mode determining curve behaviour outside the keyframe range.",
    "repeatCount": "The number of repetitions for cycle-based extrapolation modes.",
    # GltfSaveOptions properties
    "binaryMode": "When true, writes a self-contained GLB binary container; when false, writes separate JSON and binary files.",
    "flipTexCoordV": "When true, vertically flips UV coordinates on export to match DirectX-style UV conventions.",
    # GltfLoadOptions properties
    "flipTexCoordV": "When true, vertically flips UV coordinates on import to match the target renderer's UV convention.",
    # ColladaLoadOptions / ObjLoadOptions properties
    "flipCoordinateSystem": "When true, converts the coordinate system from the source format's convention (e.g. Y-up to Z-up).",
    "enableMaterials": "When true, material definitions are imported along with geometry.",
    "normalizeNormal": "When true, imported surface normals are normalised to unit length.",
    # FbxLoadOptions properties
    "keepBuiltinGlobalSettings": "When true, the FBX file's global settings node is preserved verbatim rather than mapped to the scene model.",
    # FbxSaveOptions properties
    "embedTextures": "When true, texture image data is embedded directly in the FBX file rather than referenced as external files.",
    # StlSaveOptions properties
    "binaryMode": "When true, writes binary STL output; when false, writes ASCII STL.",
    # ObjSaveOptions properties
    "applyUnitScale": "When true, applies the scene unit scale factor during export.",
    "pointCloud": "When true, exports only point positions without face connectivity.",
    "verbose": "When true, enables verbose logging during export.",
    "serializeW": "When true, includes the W component when writing normals.",
    "axisSystem": "Specifies the target axis system for coordinate conversion on export.",
    # ThreeMfSaveOptions properties
    "enableCompression": "When true, compresses the 3MF package contents using ZIP deflate.",
    "buildAll": "When true, all scene nodes are included in the 3MF build list.",
    "unit": "The length unit for the 3MF file (e.g., 'millimeter', 'inch').",
    "prettyPrint": "When true, the XML inside the 3MF package is indented for human readability.",
    # ColladaSaveOptions properties
    "indented": "When true, the COLLADA XML output is indented for human readability.",
    # ImageRenderOptions properties
    "width": "The output image width in pixels.",
    "height": "The output image height in pixels.",
    # FileSystem methods
    "createZipFileSystem(_stream, _baseDir)": "Creates a FileSystem backed by a ZIP archive stream, resolving paths relative to baseDir.",
    "readFile(_fileName, _options)": "Reads the specified file through this file system abstraction and returns its contents.",
    "writeFile(_fileName, _options)": "Writes data to the specified file through this file system abstraction.",
    "createLocalFileSystem(_directory)": "Creates a FileSystem that resolves paths relative to the given local directory.",
    "createDummyFileSystem()": "Creates a no-op FileSystem that silently ignores all read and write requests.",
    # GlobalTransform properties (some overlap with Transform)
    "translation": "The world-space translation of the node.",
    "scale": "The world-space scale of the node.",
    "rotation": "The world-space rotation quaternion of the node.",
    "transformMatrix": "The full world-space transform matrix.",
    # TextureBase properties
    "content": "The raw image data or reference held by this texture.",
    # VertexDeclaration methods
    "clear()": "Removes all vertex fields from this declaration.",
    "addField(dataType, semantic, index, alias)": "Adds a new typed vertex field with the given semantic, multi-channel index, and optional alias.",
    "fromGeometry(_geometry, _useFloat)": "Creates a vertex declaration matching the elements of the given geometry, optionally using float precision.",
    "compareTo(other)": "Returns a comparison value for ordering vertex declarations.",
    "getField(index)": "Returns the vertex field at the specified index.",
    # VertexDeclaration properties
    "sealed": "When true, the declaration is locked and no further fields can be added.",
    "size": "The total size in bytes of one vertex record described by this declaration.",
    # VertexElementFVector methods
    "setData(data)": "Replaces the element's data array with the provided values.",
    "setIndices(data)": "Replaces the element's index array with the provided values.",
    "clear()": "Clears both the data and index arrays.",
    "copyTo(target)": "Copies this element's data and indices to the target vertex element.",
    # VertexElementFVector properties
    "data": "The per-vertex or per-polygon-vertex data values.",
    "indices": "The index array used when referenceMode is INDEX or INDEX_TO_DIRECT.",
    # VertexElementUV properties
    "textureMapping": "The texture mapping slot (diffuse, normal, etc.) this UV set corresponds to.",
    "uvData": "The UV coordinates as an array of FVector2 values (x and y components only).",
    # TransformBuilder methods
    "scale(s)": "Appends or prepends a uniform scale operation.",
    "rotateDegree(angle, axis)": "Appends or prepends a rotation of the given angle in degrees around the given axis.",
    "rotateRadian(angle, axis)": "Appends or prepends a rotation of the given angle in radians around the given axis.",
    "rotateEulerRadian(x, y, z)": "Appends or prepends an Euler rotation in radians.",
    "rotateEulerDegree(degX, degY, degZ)": "Appends or prepends an Euler rotation in degrees.",
    "translate(tx, ty, tz)": "Appends or prepends a translation operation.",
    "compose(m)": "Applies the current matrix to the given matrix in-place.",
    "append(m)": "Post-multiplies the builder's matrix by m and returns this builder.",
    "prepend(m)": "Pre-multiplies the builder's matrix by m and returns this builder.",
    "rearrange(newX, newY, newZ)": "Reorders the matrix axes according to the specified new axis mapping.",
    "rotate(q)": "Appends or prepends a rotation described by a quaternion.",
    "reset()": "Resets the builder's accumulated matrix to identity.",
    # TransformBuilder properties
    "matrix": "The current accumulated transform matrix.",
    "composeOrder": "Controls whether new operations are appended (post-multiply) or prepended (pre-multiply).",
    # MathUtils methods
    "toDegree(radian)": "Converts a radian angle or Vector3 of radian angles to degrees.",
    "toRadian(degree)": "Converts a degree angle or Vector3 of degree angles to radians.",
    "calcNormal(points)": "Computes the surface normal of a polygon defined by the given points.",
    "findIntersection(p0, d0, p1, d1, results)": "Finds the closest approach between two rays and returns the distance; writes intersection parameters into results.",
    "pointInsideTriangle(p, p0, p1, p2)": "Returns true if point p lies inside the triangle defined by p0, p1, p2.",
    "rayIntersect(origin, dir, a, b)": "Tests a ray against a line segment and returns the intersection parameters, or null.",
    "clamp(val, min, max)": "Clamps val to the range [min, max] and returns the result.",
    # PolygonModifier
    "triangulate(arg1, arg2, arg3, arg4)": "Triangulates the polygons of a mesh, node, or scene and returns the result.",
    # FbxElement methods
    "getFirstElement(name)": "Returns the first child element with the given name, or null.",
    "getElements(name)": "Returns all child elements with the given name.",
    # FbxParser methods
    "parse(_data)": "Parses the token array into a hierarchical FbxProperty tree and returns the root.",
    # BinaryTokenizer methods
    "tokenize()": "Parses the binary data buffer and returns the resulting token array.",
    # FbxTokenizer methods
    "tokenize()": "Tokenises the ASCII FBX text content and returns the resulting token array.",
    # SceneObject properties
    "scene": "The scene that owns this object, or null if the object has not been attached to a scene.",
    # SemanticAttribute properties
    "semantic": "The vertex field semantic (e.g., POSITION, NORMAL, UV) for this attribute.",
    "alias": "An optional string alias for the attribute, used when the semantic alone is not unique.",
    # Watermark methods
    "encodeWatermark": "Encodes an invisible text watermark into the vertex data of the mesh.",
    "decodeWatermark": "Attempts to decode and return a previously embedded watermark string from the mesh.",
    # Rect methods
    "contains(x, y)": "Returns true if the point (x, y) lies within this rectangle.",
    # RelativeRectangle methods
    "toAbsolute(left, top, width, height)": "Resolves this relative rectangle against the given parent rectangle dimensions and returns an absolute Rect.",
    "fromScale(scaleX, scaleY, scaleWidth, scaleHeight)": "Creates a RelativeRectangle from pure scale factors with zero pixel offsets.",
    # RelativeRectangle properties
    "scaleX": "The horizontal position scale factor relative to the parent rectangle.",
    "scaleY": "The vertical position scale factor relative to the parent rectangle.",
    "scaleWidth": "The width scale factor relative to the parent rectangle.",
    "scaleHeight": "The height scale factor relative to the parent rectangle.",
    "offsetX": "The horizontal pixel offset added after applying the scale.",
    "offsetY": "The vertical pixel offset added after applying the scale.",
    "offsetWidth": "The width pixel offset added after applying the scale.",
    "offsetHeight": "The height pixel offset added after applying the scale.",
    # ColladaPlugin methods
    "getInstance()": "Returns the singleton plugin instance.",
    "createImporter()": "Creates and returns a new importer for this format.",
    "createExporter()": "Creates and returns a new exporter for this format.",
    "getFileFormat()": "Returns the FileFormat descriptor for this plugin.",
    "getImporter()": "Returns the shared importer instance registered by this plugin.",
    "getExporter()": "Returns the shared exporter instance registered by this plugin.",
    "getFormatDetector()": "Returns the format detector registered by this plugin.",
    "createLoadOptions()": "Creates and returns a default LoadOptions instance for this format.",
    "createSaveOptions()": "Creates and returns a default SaveOptions instance for this format.",
    # ColladaFormat
    "canExport()": "Returns true if this format supports exporting.",
    "canImport()": "Returns true if this format supports importing.",
    # ColladaImporter
    "importScene(scene, stream, options)": "Reads the stream and populates the given scene with the parsed geometry and materials.",
    # Vertex methods
    "compare(other)": "Compares this vertex to another for sorting purposes.",
    "readVector4(field)": "Reads a double-precision Vector4 value from the specified field.",
    "readFVector4(field)": "Reads a single-precision FVector4 value from the specified field.",
    "readVector3(field)": "Reads a double-precision Vector3 value from the specified field.",
    "readFVector3(field)": "Reads a single-precision FVector3 value from the specified field.",
    "readVector2(field)": "Reads a double-precision Vector2 value from the specified field.",
    "readFVector2(field)": "Reads a single-precision FVector2 value from the specified field.",
    "readDouble(field)": "Reads a double-precision scalar value from the specified field.",
    "readFloat(field)": "Reads a single-precision scalar value from the specified field.",
    # VertexField properties
    "semantic": "The intended use of this field (POSITION, NORMAL, UV, etc.).",
    "alias": "An optional string alias for this field.",
    "offset": "The byte offset of this field within one vertex record.",
    "index": "The multi-channel index for fields that share the same semantic (e.g., multiple UV sets).",
    # GltfAccessor properties
    "bufferView": "Index of the GltfBufferView that contains this accessor's data.",
    "byteOffset": "Byte offset from the start of the buffer view to the first element.",
    "componentType": "The OpenGL component type code (e.g., 5126 for FLOAT).",
    "count": "The number of elements described by this accessor.",
    "type": "The element type string: SCALAR, VEC2, VEC3, VEC4, MAT2, MAT3, or MAT4.",
    "min": "The minimum component values across all elements.",
    "max": "The maximum component values across all elements.",
    # GltfBufferView properties
    "buffer": "Index of the buffer this view references.",
    "byteOffset": "Byte offset from the start of the buffer.",
    "byteLength": "Length in bytes of this buffer view.",
    "target": "The GPU buffer binding target (34962 = ARRAY_BUFFER, 34963 = ELEMENT_ARRAY_BUFFER).",
    # GltfNode properties
    "mesh": "Index of the mesh attached to this node, or -1 if none.",
    "children": "Indices of child nodes in the glTF node array.",
    "translation": "Local translation as an [x, y, z] array.",
    "rotation": "Local rotation as an [x, y, z, w] quaternion array.",
    "scale": "Local scale as an [x, y, z] array.",
    # GltfPrimitive properties
    "attributes": "Map from attribute semantic name to accessor index.",
    "indices": "Accessor index for the index buffer, or -1 for non-indexed geometry.",
    "material": "Index of the material applied to this primitive.",
    "mode": "The OpenGL draw mode (e.g., 4 = TRIANGLES).",
    # GltfMaterial properties
    "pbrMetallicRoughness": "The PBR metallic-roughness parameters for this material.",
    "emissiveFactor": "The emissive colour as an [R, G, B] array.",
    "alphaMode": "The alpha blending mode: OPAQUE, MASK, or BLEND.",
    "alphaCutoff": "The alpha cutoff threshold used when alphaMode is MASK.",
    # GltfScene properties
    "nodes": "Indices of root nodes in this scene.",
    # GltfMesh properties
    "primitives": "The list of primitives (draw calls) that make up this mesh.",
    # GltfData properties
    "asset": "The glTF asset metadata object containing version and generator strings.",
    "scene": "The index of the default scene.",
    "scenes": "All scenes defined in the glTF document.",
    "accessors": "All accessors defined in the glTF document.",
    "bufferViews": "All buffer views defined in the glTF document.",
    "buffers": "All buffers defined in the glTF document.",
    "materials": "All materials defined in the glTF document.",
    # FbxFormat properties
    "extension": "The primary file extension for this format (e.g., 'fbx').",
    "extensions": "All file extensions recognised by this format.",
    "contentType": "The MIME content type string for this format.",
    "fileFormatType": "An internal type descriptor used to identify the format.",
    "version": "The format version string.",
    "canExport": "True if this format supports exporting.",
    "canImport": "True if this format supports importing.",
    "formats": "All format variants registered under this descriptor.",
    # BoundingBoxExtent properties
    "extentX": "The extent value on the X axis.",
    "extentY": "The extent value on the Y axis.",
    "extentZ": "The extent value on the Z axis.",
    # Extrapolation / ExtrapolationType
    "CONSTANT": "Holds the boundary keyframe value outside the animation range.",
    "GRADIENT": "Extrapolates linearly beyond the boundary using the tangent slope.",
    "CYCLE": "Repeats the animation from the beginning after each cycle.",
    "CYCLE_RELATIVE": "Repeats the animation while accumulating the total value change each cycle.",
    "OSCILLATE": "Alternates the animation forward and backward (ping-pong).",
    # StepMode
    "PREVIOUS_VALUE": "Uses the current keyframe's value until the next keyframe is reached.",
    "NEXT_VALUE": "Jumps immediately to the next keyframe's value.",
    # LightType
    "POINT": "An omnidirectional point light that emits equally in all directions.",
    "DIRECTIONAL": "A directional light that emits parallel rays from infinite distance.",
    "SPOT": "A cone-shaped spot light.",
    "AREA": "A planar area light source.",
    "VOLUME": "A volumetric light that fills a defined volume.",
    # ProjectionType
    "PERSPECTIVE": "Standard perspective projection with foreshortening.",
    "ORTHOGRAPHIC": "Parallel (orthographic) projection without depth distortion.",
    # ApertureMode
    "HORIZONTAL": "Field of view is derived from the horizontal aperture size.",
    "VERTICAL": "Field of view is derived from the vertical aperture size.",
    "HORZ_AND_VERT": "Both horizontal and vertical aperture sizes are used to compute the field of view.",
    # RotationMode
    "FIXED": "The camera direction is fixed and does not orbit.",
    "ORBIT": "The camera orbits around its target point.",
    # MappingMode
    "CONTROL_POINT": "One data value per control point (vertex).",
    "POLYGON_VERTEX": "One data value per polygon corner (per-face vertex).",
    "POLYGON": "One data value per polygon face.",
    "EDGE": "One data value per edge.",
    "ALL_SAME": "A single data value applied to all geometry elements.",
    # ReferenceMode
    "DIRECT": "Data values correspond directly to the mapping element indices.",
    "INDEX": "An explicit index array maps from mapping elements to data values.",
    "INDEX_TO_DIRECT": "An index array maps to data values stored in a separate direct array.",
    # ComposeOrder
    "APPEND": "Each new transform is post-multiplied (applied after the current matrix).",
    "PREPEND": "Each new transform is pre-multiplied (applied before the current matrix).",
    # ColladaTransformStyle
    "COMPONENTS": "Transforms are written as separate translate, rotate, and scale elements.",
    "MATRIX": "Transforms are written as a single matrix element.",
    # BooleanOperation
    "ADD": "Computes the union of two meshes.",
    "SUB": "Subtracts one mesh from another.",
    "INTERSECT": "Computes the intersection of two meshes.",
    # SplitMeshPolicy
    "ADJUST": "Reindexes vertex element data when splitting a mesh by material.",
    "CLONE_DATA": "Duplicates vertex element data for each sub-mesh when splitting.",
    # AnimationChannel properties
    "componentType": "The data type of the animated property component.",
    "defaultValue": "The default value used when no keyframe is active.",
    "keyframeSequence": "The keyframe sequence providing the animated values for this channel.",
    # Interpolation enum values
    "LINEAR": "Linear interpolation between keyframes.",
    "BEZIER": "Cubic Bezier interpolation using tangent handles.",
    "B_SPLINE": "B-spline interpolation for smooth curves without explicit tangents.",
    "CARDINAL_SPLINE": "Cardinal spline interpolation with automatic tangent calculation.",
    "TCB_SPLINE": "Tension-continuity-bias (Kochanek-Bartels) spline interpolation.",
    # VertexElementType
    "BINORMAL": "Binormal vector channel, used with normals and tangents for tangent space.",
    "NORMAL": "Surface normal vector channel.",
    "TANGENT": "Tangent vector channel, perpendicular to the normal.",
    "MATERIAL": "Per-polygon material index channel.",
    "POLYGON_GROUP": "Per-polygon group membership channel.",
    "UV": "UV texture coordinate channel.",
    "VERTEX_COLOR": "Per-vertex or per-polygon-vertex colour channel.",
    "SMOOTHING_GROUP": "Per-polygon smoothing group ID channel.",
    "VERTEX_CREASE": "Per-vertex crease weight for subdivision surface rendering.",
    "EDGE_CREASE": "Per-edge crease weight for subdivision surface rendering.",
    "USER_DATA": "Custom user-defined data channel.",
    "VISIBILITY": "Per-vertex or per-polygon visibility flag channel.",
    "SPECULAR": "Per-vertex specular intensity channel.",
    "WEIGHT": "Per-vertex skinning weight channel.",
    "HOLE": "Per-polygon hole flag channel (marks faces as holes in the surface).",
    # TextureMapping
    "AMBIENT": "UV set used for ambient occlusion or ambient colour texture.",
    "EMISSIVE": "UV set used for the emissive (self-illumination) texture.",
    "DIFFUSE": "UV set used for the diffuse colour texture.",
    "OPACITY": "UV set used for the opacity/transparency texture.",
    "BUMP": "UV set used for bump map texture.",
    "NORMAL": "UV set used for the normal map texture.",
    "SPECULAR": "UV set used for the specular colour texture.",
    "GLOW": "UV set used for the glow or emissive intensity texture.",
    "REFLECTION": "UV set used for the reflection environment texture.",
    "SHADOW": "UV set used for shadow map projection.",
    "SHININESS": "UV set used for the shininess (glossiness) texture.",
    "DISPLACEMENT": "UV set used for displacement map texture.",
    # Axis
    "POSITIVE_X": "The positive X axis direction.",
    "NEGATIVE_X": "The negative X axis direction.",
    "POSITIVE_Y": "The positive Y axis direction.",
    "NEGATIVE_Y": "The negative Y axis direction.",
    "POSITIVE_Z": "The positive Z axis direction.",
    "NEGATIVE_Z": "The negative Z axis direction.",
    # RotationOrder
    "XYZ": "Rotations applied in X then Y then Z order.",
    "XZY": "Rotations applied in X then Z then Y order.",
    "YZX": "Rotations applied in Y then Z then X order.",
    "YXZ": "Rotations applied in Y then X then Z order.",
    "ZXY": "Rotations applied in Z then X then Y order.",
    "ZYX": "Rotations applied in Z then Y then X order.",
    # WeightedMode
    "NONE": "Tangent weights are normalised; standard non-weighted Bezier interpolation.",
    "RIGHT": "The outgoing tangent has an explicit time weight.",
    "NEXT_LEFT": "The incoming tangent at the next keyframe has an explicit time weight.",
    "BOTH": "Both the outgoing and incoming tangents have explicit time weights.",
    # FbxProperty properties
    "name": "The name of this FBX property or element.",
    "properties": "Nested child properties within this FBX element.",
    # FbxParser properties
    "rootScope": "The root FbxElement produced after parsing.",
    # FbxTokenizer properties (constructor)
    "content": "The ASCII FBX text content to tokenise.",
    # IOExtension (no members)
    # IIndexedVertexElement
    "indices": "The index array that maps from geometry elements to data values.",
    # INamedObject
    # Light properties
    "lightType": "The type of light source: POINT, DIRECTIONAL, SPOT, AREA, or VOLUME.",
    # AssetInfo constructor
    # ImageRenderOptions already covered
    # GltfBufferView property
    "byteStride": "The byte stride between consecutive elements in the buffer view, or 0 for tightly packed.",
    # ParseException
    # PolygonModifier note: only one method
    # Camera methods
    "moveForward(_distance)": "Moves the camera forward along its view direction by the specified distance.",
    # VertexField
    "dataType": "The data type of this vertex field (e.g., VECTOR3, F_VECTOR2).",
    # SemanticAttribute constructor
    # ObjSaveOptions already covered
    # RelativeRectangle already covered
    # Watermark
    "encodeWatermark(mesh, text, password)": "Encodes an invisible text watermark into the vertex data of the given mesh.",
    "decodeWatermark(mesh, password)": "Attempts to decode and return a watermark string embedded in the mesh's vertex data.",
}


def get_class_name_from_file(path: Path) -> str:
    """Extract class name from frontmatter linkTitle."""
    content = path.read_text(encoding="utf-8")
    m = re.search(r'^linkTitle:\s*(.+)$', content, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return path.stem


def expand_overview(content: str, class_name: str) -> str:
    """Replace thin overview with rich prose."""
    prose = CLASS_OVERVIEWS.get(class_name)
    if not prose:
        return content

    # Match the existing Overview section up to the first --- or ##
    old_pattern = re.compile(
        r'(## Overview\n\n)'           # heading
        r'(`[^`]+` is a class[^\n]*\.\s*(?:Inherits from: `[^`]+`\.\s*)?)\n\n'
        r'(\*\*Package\*\*:[^\n]+\n)',
        re.DOTALL
    )

    # We want to insert prose between the terse one-liner and the Package line.
    def replacer(m):
        heading = m.group(1)
        terse = m.group(2)
        pkg = m.group(3)
        return f"{heading}{terse}\n\n{prose}\n\n{pkg}"

    new_content, count = old_pattern.subn(replacer, content)
    if count > 0:
        return new_content

    # Fallback: try simpler pattern (class line + package line with no blank between)
    old_pattern2 = re.compile(
        r'(## Overview\n\n)'
        r'(`[^`]+` is a class[^\n]*\.)\n\n'
        r'(\*\*Package\*\*:[^\n]+\n)',
    )
    new_content, count = old_pattern2.subn(replacer, content)
    if count > 0:
        return new_content

    return content


def fill_empty_table_cells(content: str) -> str:
    """Fill empty description cells in method/property tables."""
    lines = content.split('\n')
    result = []
    in_methods = False
    in_properties = False

    for line in lines:
        # Track which section we're in
        if re.match(r'^## Methods', line):
            in_methods = True
            in_properties = False
        elif re.match(r'^## Properties', line):
            in_methods = False
            in_properties = True
        elif re.match(r'^## ', line):
            in_methods = False
            in_properties = False

        if (in_methods or in_properties) and line.strip().startswith('|') and line.strip().endswith('|  |'):
            # Row ends with an empty cell
            parts = [p.strip() for p in line.split('|')]
            # parts[0] is empty (before first |), last is empty (after last |)
            # Remove empty boundaries
            cells = [p for p in parts if p != '']

            if in_methods and len(cells) >= 3:
                # method | returns | description
                sig = cells[0].strip('`').strip()
                desc = find_description(sig)
                if desc:
                    # Rebuild line with description
                    line = rebuild_method_row(line, desc)

            elif in_properties and len(cells) >= 4:
                # name | type | access | description
                prop_name = cells[0].strip('`').strip()
                desc = find_description(prop_name)
                if desc:
                    line = rebuild_prop_row(line, desc)

        result.append(line)
    return '\n'.join(result)


def find_description(sig: str) -> str:
    """Try to find a description for a method signature or property name."""
    # Direct lookup
    if sig in MEMBER_DESCRIPTIONS:
        return MEMBER_DESCRIPTIONS[sig]

    # Try matching by method name prefix (strip params)
    method_name = sig.split('(')[0].strip()
    for key, val in MEMBER_DESCRIPTIONS.items():
        key_name = key.split('(')[0].strip()
        if key_name == method_name:
            return val

    return ""


def rebuild_method_row(line: str, desc: str) -> str:
    """Replace trailing |  | with | desc |"""
    # The line ends with "|  |" — replace last empty cell
    return line[:-3] + desc + ' |'


def rebuild_prop_row(line: str, desc: str) -> str:
    """Replace trailing |  | with | desc |"""
    return line[:-3] + desc + ' |'


def process_file(path: Path) -> tuple[bool, str]:
    """Process one reference page. Returns (changed, reason)."""
    if path.name == '_index.md':
        return False, "skipped index"

    content = path.read_text(encoding="utf-8")
    class_name = get_class_name_from_file(path)

    original = content

    # 1. Expand Overview section
    content = expand_overview(content, class_name)

    # 2. Fill empty table cells
    content = fill_empty_table_cells(content)

    if content != original:
        path.write_text(content, encoding="utf-8")
        update_mechanism(path, "agent-edit")
        return True, "expanded"
    return False, "no changes needed"


def main():
    pages = sorted(REF_DIR.glob("*.md"))
    changed = 0
    skipped = 0
    unchanged = 0

    for page in pages:
        ok, reason = process_file(page)
        if ok:
            changed += 1
            print(f"  EXPANDED  {page.name}")
        elif "skipped" in reason:
            skipped += 1
        else:
            unchanged += 1
            print(f"  unchanged {page.name}")

    print(f"\nDone. Changed={changed}  Unchanged={unchanged}  Skipped={skipped}")


if __name__ == "__main__":
    main()
