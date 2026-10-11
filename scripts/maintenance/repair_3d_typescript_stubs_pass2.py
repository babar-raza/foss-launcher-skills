#!/usr/bin/env python3
"""
Pass 2: Fill remaining empty table cells using method-name-only matching.
The first pass expanded Overview sections but left many table cells empty
because exact signature matching failed. This pass uses a simpler approach:
extract only the method/property name and look it up.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "pipeline"))
from provenance import update_mechanism

BASE = Path("D:/onedrive/Documents/GitHub/aspose.org")
REF_DIR = BASE / "content/reference.aspose.org/en/3d/typescript"

# Keyed by method/property name only (no params/types).
# Where the same name appears with different meanings per context, we use
# the most general description (properties vs. methods are distinguished by
# the table section we're in).
METHOD_DESCS = {
    # Universal
    "toString": "Returns a human-readable string representation of this object.",
    "findProperty": "Searches the property collection for a property with the given name and returns it, or null if not found.",
    "getProperty": "Returns the current value of the named property.",
    "setProperty": "Sets the value of the named property, creating it if it does not already exist.",
    "removeProperty": "Removes the specified property from the collection and returns true if it was present.",
    "getBoundingBox": "Computes and returns the axis-aligned bounding box enclosing this object.",
    "getEntityRendererKey": "Returns an internal renderer key used to identify the entity type during rendering.",
    # Scene
    "clear": "Removes all content from the scene, resetting it to an empty state.",
    "createAnimationClip": "Creates and registers a new named animation clip in the scene.",
    "getAnimationClip": "Returns the animation clip with the given name, or null if none exists.",
    "open": "Loads 3D content from a file path or stream, populating this scene with the parsed data.",
    "openFromBuffer": "Loads 3D content from an in-memory byte buffer, populating this scene with the parsed data.",
    "save": "Writes this scene to a file path or stream using the specified format or save options.",
    "saveToBuffer": "Serialises this scene to a Buffer in the specified format and returns the result.",
    "render": "Renders a still image of the scene from the given camera viewpoint to a file or bitmap.",
    "fromFile": "Static factory: opens the specified file and returns a populated Scene instance.",
    "_propagateScene": "Internal method that propagates scene ownership through the object graph.",
    # Node
    "addEntity": "Attaches an entity (mesh, light, camera, etc.) to this node.",
    "removeEntity": "Detaches the specified entity from this node.",
    "clearEntities": "Removes all attached entities from this node.",
    "addChildNode": "Appends an existing node as a child of this node.",
    "createChildNode": "Creates a new named child node with an optional entity and material already attached.",
    "getChild": "Returns the child node at the given index or with the given name, or null if not found.",
    "merge": "Merges all children and entities from the given node into this node.",
    "evaluateGlobalTransform": "Computes and returns the accumulated world-space transform matrix for this node.",
    "selectSingleObject": "Evaluates a path expression against the scene graph and returns the first matching object.",
    "selectObjects": "Evaluates a path expression against the scene graph and returns all matching objects.",
    # Mesh
    "createPolygon": "Appends a new polygon to the mesh using the currently accumulated control point indices.",
    "getPolygonSize": "Returns the number of vertices in the polygon at the specified index.",
    "toMesh": "Returns this mesh object (identity operation; satisfies the geometry conversion interface).",
    "optimize": "Welds duplicate vertices within the given tolerances and returns the optimised mesh.",
    "doBoolean": "Performs a CSG boolean operation (union, subtraction, or intersection) on two meshes and returns the result.",
    "isManifold": "Returns true if the mesh surface is manifold (every edge is shared by exactly two faces).",
    "union": "Returns the CSG union of two meshes.",
    "difference": "Returns the CSG subtraction of mesh b from mesh a.",
    "intersect": "Returns the CSG intersection of two meshes.",
    "triangulate": "Converts all polygons to triangles and returns the result.",
    # Transform
    "setTranslation": "Sets the local translation of this node and returns the Transform for chaining.",
    "setScale": "Sets the local scale of this node and returns the Transform for chaining.",
    "setEulerAngles": "Sets the local rotation from Euler angles (degrees) and returns the Transform for chaining.",
    "setRotation": "Sets the local rotation from a quaternion and returns the Transform for chaining.",
    "setPreRotation": "Sets the pre-rotation offset applied before the main rotation.",
    "setPostRotation": "Sets the post-rotation offset applied after the main rotation.",
    "setGeometricTranslation": "Sets a geometric translation that offsets geometry without affecting child-node transforms.",
    "setGeometricScaling": "Sets a geometric scale that resizes geometry without affecting child-node transforms.",
    "setGeometricRotation": "Sets a geometric rotation that rotates geometry without affecting child-node transforms.",
    "_computeMatrix": "Internal method that recomputes the cached local transform matrix from component values.",
    "_invalidateCache": "Internal method that marks the cached transform matrix as stale, triggering recomputation.",
    # Matrix4
    "getItem": "Returns the element at the given index.",
    "setItem": "Sets the element at the given index.",
    "transpose": "Returns the transpose of this matrix.",
    "concatenate": "Returns the product of this matrix and the argument (matrix multiplication).",
    "normalize": "Normalises the rotation component and returns the result.",
    "inverse": "Returns the inverse of this matrix or quaternion.",
    "decompose": "Decomposes this matrix into its translation, scaling, and rotation components.",
    "setTRS": "Sets this matrix from translation, rotation quaternion, and scale vectors.",
    "toArray": "Returns the matrix elements as a flat 16-element array in row-major order.",
    "identity": "Returns the 4×4 identity matrix.",
    "translate": "Returns a translation matrix or applies a translation transform.",
    "scale": "Returns a scaling matrix or applies a scaling transform.",
    "rotateFromEuler": "Returns a rotation matrix constructed from Euler angles in radians.",
    "rotate": "Returns a rotation matrix for the given angle or quaternion.",
    "equals": "Returns true if all elements of this object equal those of the other.",
    # Quaternion
    "conjugate": "Returns the conjugate of this quaternion (negated vector part).",
    "dot": "Returns the dot product.",
    "concat": "Returns the product of this quaternion and rhs (rotation composition).",
    "eulerAngles": "Returns the rotation expressed as Euler angles (pitch, yaw, roll) in radians.",
    "fromEulerAngle": "Returns a quaternion constructed from the given Euler angles in radians.",
    "fromAngleAxis": "Returns a quaternion representing a rotation of angle radians around the given axis.",
    "fromRotation": "Returns the quaternion that rotates the orig direction to the dest direction.",
    "interpolate": "Returns a linearly interpolated quaternion between two quaternions.",
    "slerp": "Returns the spherical linear interpolation between two quaternions at parameter t.",
    "toMatrix": "Returns the equivalent rotation Matrix4 for this quaternion.",
    "IDENTITY": "Returns the identity quaternion (no rotation).",
    # Vector
    "set": "Sets all components in place.",
    "cross": "Returns the cross product of this vector and rhs.",
    "angleBetween": "Returns the angle in radians between this vector and another.",
    "sin": "Returns a vector with component-wise sine applied.",
    "cos": "Returns a vector with component-wise cosine applied.",
    "compareTo": "Returns a negative, zero, or positive value for ordering purposes.",
    "parse": "Parses a string representation and returns the corresponding object.",
    "minus": "Returns the result of subtracting the argument from this vector.",
    "times": "Returns this vector scaled by the given scalar.",
    "length": "Returns the magnitude (Euclidean length) of this vector or quaternion.",
    "add": "Returns the sum of this vector and the argument.",
    "sub": "Returns the difference of this vector and the argument.",
    "mul": "Returns this vector multiplied by a scalar.",
    "div": "Returns this vector divided by a scalar.",
    # Vector factories
    "zero": "Returns the zero vector (0, 0, 0).",
    "one": "Returns the ones vector (1, 1, 1).",
    "unitX": "Returns the unit vector along the X axis (1, 0, 0).",
    "unitY": "Returns the unit vector along the Y axis (0, 1, 0).",
    "unitZ": "Returns the unit vector along the Z axis (0, 0, 1).",
    # BoundingBox
    "null": "Returns a null (empty) bounding box with no defined extents.",
    "infinite": "Returns a bounding box or extent representing infinite extent.",
    "finite": "Returns a finite bounding box extent.",
    "merge": "Expands this bounding box to include the given point or box.",
    "contains": "Returns true if the given point or bounding box lies within this bounding box.",
    "overlapsWith": "Returns true if this bounding box overlaps with the given box.",
    "getCenter": "Returns the geometric centre of this bounding box.",
    "getSize": "Returns the dimensions of this bounding box as a vector.",
    # Geometry
    "addControlPoint": "Appends a new control point (vertex position) to the geometry's vertex list.",
    "createElement": "Creates and attaches a new typed vertex element channel to this geometry.",
    "createElementUV": "Creates and attaches a new UV vertex element for the specified texture mapping slot.",
    "addElement": "Adds an already-constructed vertex element to this geometry.",
    "getElement": "Returns the first vertex element of the specified type, or null if none exists.",
    "getVertexElementOfUV": "Returns the UV vertex element associated with the specified texture mapping slot, or null.",
    # Material
    "getTexture": "Returns the texture assigned to the named slot, or null if none is set.",
    "setTexture": "Assigns a texture to the named slot.",
    "fromMaterial": "Static factory: converts a legacy Material to a PbrMaterial.",
    # IO
    "supportsFormat": "Returns true if this importer or exporter supports the specified file format.",
    "export": "Serialises the given scene to the output stream in this exporter's format.",
    "importScene": "Reads the stream and populates the given scene with the parsed geometry and materials.",
    "canExport": "Returns true if this format supports exporting.",
    "canImport": "Returns true if this format supports importing.",
    "getInstance": "Returns the singleton instance of this class.",
    "createLoadOptions": "Creates and returns a default LoadOptions instance for this format.",
    "createSaveOptions": "Creates and returns a default SaveOptions instance for this format.",
    "createImporter": "Creates and returns a new importer for this format.",
    "createExporter": "Creates and returns a new exporter for this format.",
    "getFileFormat": "Returns the FileFormat descriptor for this plugin.",
    "getImporter": "Returns the shared importer instance registered by this plugin.",
    "getExporter": "Returns the shared exporter instance registered by this plugin.",
    "getFormatDetector": "Returns the format detector registered by this plugin.",
    "detect": "Inspects the stream or file name to determine whether it matches this format.",
    "extension": "Returns the primary file extension for this format.",
    "extensions": "Returns all file extensions recognised by this format.",
    "version": "Returns the format version string.",
    # IOService
    "instance": "Returns the singleton IOService instance.",
    "registerExporter": "Registers a custom exporter with the I/O service.",
    "registerImporter": "Registers a custom importer with the I/O service.",
    "registerDetector": "Registers a custom format detector with the I/O service.",
    "registerPlugin": "Registers all components of a format plugin in one call.",
    "detectFormat": "Inspects the stream and file name to determine the file format; returns null if unknown.",
    "createExporter": "Creates and returns an exporter for the specified file format.",
    "createImporter": "Creates and returns an importer for the specified file format.",
    "getPluginForFormat": "Returns the plugin that handles the specified file format, or null.",
    "getPluginForExtension": "Returns the plugin associated with the given file extension, or null.",
    "getAllPlugins": "Returns all registered format plugins.",
    # FileSystem
    "createZipFileSystem": "Creates a FileSystem backed by a ZIP archive stream.",
    "readFile": "Reads the specified file through this file system abstraction.",
    "writeFile": "Writes data to the specified file through this file system abstraction.",
    "createLocalFileSystem": "Creates a FileSystem that resolves paths relative to the given local directory.",
    "createDummyFileSystem": "Creates a no-op FileSystem that silently ignores all read and write requests.",
    # AnimationNode
    "findBindPoint": "Searches for a bind point on the target object; returns null if not found.",
    "getBindPoint": "Returns the bind point for the named property on the target, optionally creating it.",
    "createBindPoint": "Creates and returns a new bind point connecting the named property of the target object.",
    "getKeyframeSequence": "Retrieves or optionally creates the keyframe sequence for the specified property channel.",
    # BindPoint
    "addChannel": "Adds an animation channel with the given name and default value.",
    "bindKeyframeSequence": "Associates an existing keyframe sequence with the named animation channel.",
    "getChannel": "Returns the animation channel with the given name, or null.",
    "resetChannels": "Removes all animation channels from this bind point.",
    "createKeyframeSequence": "Creates and returns a new keyframe sequence for the named channel.",
    # KeyframeSequence
    "reset": "Removes all keyframes from this sequence or resets the builder matrix to identity.",
    "add": "Appends a new keyframe at the given time with the specified value and interpolation mode.",
    "setBindPoint": "Sets the bind point that owns this keyframe sequence.",
    # Property
    "getExtra": "Returns the extra metadata value associated with the given name on this property.",
    "setExtra": "Associates a metadata value with the given name on this property.",
    # PropertyCollection
    "get": "Returns the current value of the named property.",
    # PolygonModifier
    "triangulate": "Converts polygon geometry to triangles and returns the result.",
    # FbxElement
    "getFirstElement": "Returns the first child element with the given name, or null.",
    "getElements": "Returns all child elements with the given name.",
    # FbxParser
    "parse": "Parses the token array into a hierarchical structure and returns the root.",
    # BinaryTokenizer / FbxTokenizer
    "tokenize": "Tokenises the input content and returns the resulting token array.",
    # Camera
    "moveForward": "Moves this camera forward along its view direction by the specified distance.",
    # TransformBuilder
    "rotateDegree": "Appends or prepends a rotation of the given angle in degrees around the given axis.",
    "rotateRadian": "Appends or prepends a rotation of the given angle in radians around the given axis.",
    "rotateEulerRadian": "Appends or prepends an Euler rotation in radians.",
    "rotateEulerDegree": "Appends or prepends an Euler rotation in degrees.",
    "compose": "Applies the current matrix to the given matrix in-place.",
    "append": "Post-multiplies the builder's matrix by m and returns this builder.",
    "prepend": "Pre-multiplies the builder's matrix by m and returns this builder.",
    "rearrange": "Reorders the matrix axes according to the specified new axis mapping.",
    # MathUtils
    "toDegree": "Converts radian angles to degrees.",
    "toRadian": "Converts degree angles to radians.",
    "calcNormal": "Computes the surface normal of a polygon defined by the given points.",
    "findIntersection": "Finds the closest approach between two rays and writes parameters into results.",
    "pointInsideTriangle": "Returns true if point p lies inside the given triangle.",
    "rayIntersect": "Tests a ray against a line segment; returns intersection parameters or null.",
    "clamp": "Clamps a value to the range [min, max].",
    # Vertex
    "compare": "Compares this vertex to another for sorting purposes.",
    "readVector4": "Reads a double-precision Vector4 value from the specified vertex field.",
    "readFVector4": "Reads a single-precision FVector4 value from the specified vertex field.",
    "readVector3": "Reads a double-precision Vector3 value from the specified vertex field.",
    "readFVector3": "Reads a single-precision FVector3 value from the specified vertex field.",
    "readVector2": "Reads a double-precision Vector2 value from the specified vertex field.",
    "readFVector2": "Reads a single-precision FVector2 value from the specified vertex field.",
    "readDouble": "Reads a double-precision scalar value from the specified vertex field.",
    "readFloat": "Reads a single-precision scalar value from the specified vertex field.",
    # VertexDeclaration
    "addField": "Adds a new typed vertex field with the given semantic, index, and optional alias.",
    "fromGeometry": "Creates a vertex declaration matching the elements of the given geometry.",
    "getField": "Returns the vertex field at the specified index.",
    # VertexElementFVector
    "setData": "Replaces the element's data array with the provided values.",
    "setIndices": "Replaces the element's index array with the provided values.",
    "copyTo": "Copies this element's data and indices to the target vertex element.",
    # VertexElementUV
    "addData": "Appends a UV data value to the element's data array.",
    # Rect
    "toAbsolute": "Resolves this relative rectangle against the given parent dimensions and returns an absolute Rect.",
    "fromScale": "Creates a RelativeRectangle from pure scale factors with zero pixel offsets.",
    # ColladaTransformStyle
    "COMPONENTS": "Returns the ColladaTransformStyle for component-based (translate/rotate/scale) output.",
    "MATRIX": "Returns the ColladaTransformStyle for matrix-based transform output.",
    # ThreeMfFormat
    "isBuildable": "Returns true if the given node is included in the 3MF build list.",
    "getTransformForBuild": "Returns the build transform for the given node, or null if not set.",
    "setBuildable": "Marks the given node as buildable and sets its build transform.",
    "setObjectType": "Sets the 3MF object type for the given node (e.g., 'model', 'support').",
    "getObjectType": "Returns the 3MF object type assigned to the given node.",
    # Watermark
    "encodeWatermark": "Encodes an invisible text watermark into the vertex data of a mesh.",
    "decodeWatermark": "Decodes and returns a watermark string embedded in the mesh's vertex data.",
    # SemanticAttribute
    "SemanticAttribute": "Creates a new SemanticAttribute associating a semantic with an optional alias.",
    # AnimationClip
    "createAnimationNode": "Creates and returns a new named animation node within this clip.",
    # RotationOrder
    "XYZ": "Returns the XYZ rotation order value.",
    "XZY": "Returns the XZY rotation order value.",
    "YZX": "Returns the YZX rotation order value.",
    "YXZ": "Returns the YXZ rotation order value.",
    "ZXY": "Returns the ZXY rotation order value.",
    "ZYX": "Returns the ZYX rotation order value.",
    # Axis
    "POSITIVE_X": "Returns the positive X axis direction.",
    "NEGATIVE_X": "Returns the negative X axis direction.",
    "POSITIVE_Y": "Returns the positive Y axis direction.",
    "NEGATIVE_Y": "Returns the negative Y axis direction.",
    "POSITIVE_Z": "Returns the positive Z axis direction.",
    "NEGATIVE_Z": "Returns the negative Z axis direction.",
    # FVector2/FVector3/FVector4
    "normalize": "Returns a unit vector in the same direction.",
    # ColladaImporter
    "openFromStream": "Loads 3D content from a stream into a Scene and returns it.",
}

PROP_DESCS = {
    # A3DObject / SceneObject
    "name": "The unique name identifying this object.",
    "properties": "The dynamic property bag attached to this object.",
    "scene": "The scene that owns this object, or null if not attached to a scene.",
    # Scene
    "VERSION": "The library version string for the @aspose/3d package.",
    "rootNode": "The root node of the scene graph; all scene-object nodes descend from this node.",
    "subScenes": "Additional child scenes embedded within this document.",
    "library": "A collection of custom objects stored in the scene library.",
    "assetInfo": "Document-level metadata such as creator, dates, and unit information.",
    "animationClips": "All animation clips registered in this scene.",
    "currentAnimationClip": "The animation clip currently selected for playback; may be null.",
    "poses": "Pose objects stored in the scene, used for reference poses.",
    # Node
    "parentNode": "The parent node in the scene graph hierarchy, or null for the root node.",
    "childNodes": "An array of all direct child nodes.",
    "entities": "All entities attached to this node.",
    "entity": "The primary entity attached to this node, or undefined if none.",
    "materials": "The list of materials assigned to this node.",
    "material": "The primary material assigned to this node, or null if none.",
    "transform": "The local transform (position, rotation, scale) of this node.",
    "globalTransform": "The computed world-space transform of this node.",
    "visible": "Whether this node or geometry is visible during rendering.",
    "excluded": "When true, excludes this node from rendering and bounding-box calculations.",
    "metaDatas": "Application-defined metadata objects attached to this node.",
    "parentNodes": "All parent nodes this entity is attached to (multi-instancing).",
    # Transform
    "translation": "The local or world-space translation vector.",
    "scaling": "The local scale vector.",
    "rotation": "The local or world-space rotation as a Quaternion.",
    "eulerAngles": "The local or world-space rotation expressed as Euler angles in degrees.",
    "scalingOffset": "The offset applied to the scaling pivot point.",
    "scalingPivot": "The pivot point around which scaling is applied.",
    "rotationOffset": "The offset applied to the rotation pivot point.",
    "rotationPivot": "The pivot point around which rotation is applied.",
    "preRotation": "A fixed pre-rotation applied before the animated rotation.",
    "postRotation": "A fixed post-rotation applied after the animated rotation.",
    "geometricTranslation": "A translation applied to geometry only, not propagated to child nodes.",
    "geometricScaling": "A scale applied to geometry only, not propagated to child nodes.",
    "geometricRotation": "A rotation applied to geometry only, not propagated to child nodes.",
    "transformMatrix": "The full composed local or world-space transform as a Matrix4.",
    # GlobalTransform
    "scale": "The world-space scale vector.",
    # Geometry
    "castShadows": "Whether this geometry casts shadows in shadow-enabled renders.",
    "receiveShadows": "Whether this geometry receives shadows cast by other objects.",
    "vertexElements": "All vertex element channels (normals, UVs, colours, etc.) attached to this geometry.",
    "controlPoints": "The vertex positions as an array of Vector4 values.",
    # Mesh
    "edges": "The edge list as pairs of vertex indices.",
    "polygonCount": "The total number of polygons in the mesh.",
    "polygons": "The polygon definitions as an array of vertex-index arrays.",
    "deformers": "Deformer objects (e.g., skinning) applied to this mesh.",
    # Entity
    "parentNode": "The primary parent node this entity is attached to.",
    # Material
    "MAP_SPECULAR": "Slot name constant for the specular texture channel.",
    "MAP_DIFFUSE": "Slot name constant for the diffuse colour texture channel.",
    "MAP_EMISSIVE": "Slot name constant for the emissive texture channel.",
    "MAP_AMBIENT": "Slot name constant for the ambient texture channel.",
    "MAP_NORMAL": "Slot name constant for the normal map texture channel.",
    # LambertMaterial
    "emissiveColor": "The self-illumination colour of the material.",
    "ambientColor": "The ambient reflectance colour of the material.",
    "diffuseColor": "The primary diffuse reflectance colour of the material.",
    "transparentColor": "The transparency colour used for chromatic transparency.",
    "transparency": "The overall transparency factor from 0 (opaque) to 1 (fully transparent).",
    # PhongMaterial
    "specularColor": "The specular highlight colour of the material.",
    "specularFactor": "A scalar multiplier for the specular colour contribution.",
    "shininess": "The Phong shininess exponent controlling the size of specular highlights.",
    "reflectionColor": "The reflection colour used for environment reflections.",
    "reflectionFactor": "A scalar multiplier for the reflection colour contribution.",
    # PbrMaterial
    "albedo": "The base colour (albedo) of the PBR material as a Vector3 RGB value.",
    "albedoTexture": "A texture that multiplies the albedo colour.",
    "normalTexture": "A normal map texture for surface detail.",
    "metallicFactor": "The metallic factor from 0 (dielectric) to 1 (fully metallic).",
    "roughnessFactor": "The roughness factor from 0 (smooth) to 1 (fully rough).",
    "metallicRoughness": "A combined metallic-roughness texture (B channel = metallic, G = roughness).",
    "occlusionTexture": "An ambient occlusion texture (R channel) that darkens indirect lighting.",
    "occlusionFactor": "A scalar multiplier for the occlusion texture strength.",
    "emissiveTexture": "A texture for self-illumination, multiplied by the emissive colour.",
    # Camera
    "rotationMode": "The rotation mode controlling whether the camera orbits or is fixed.",
    "nearPlane": "The distance to the near clipping plane.",
    "farPlane": "The distance to the far clipping plane.",
    "aspect": "The camera's aspect ratio (width divided by height).",
    "orthoHeight": "The height of the orthographic view volume in world units.",
    "up": "The up vector that defines the camera's vertical orientation.",
    "lookAt": "The world-space point the camera is aimed at.",
    "direction": "The view direction vector of the camera.",
    "target": "A node that the camera tracks.",
    "apertureMode": "Controls how fieldOfView is derived from the camera's aperture dimensions.",
    "fieldOfView": "The diagonal field of view angle in degrees for perspective projection.",
    "fieldOfViewX": "The horizontal field of view angle in degrees.",
    "fieldOfViewY": "The vertical field of view angle in degrees.",
    "width": "The aperture width or image width in pixels.",
    "height": "The aperture height or image height in pixels.",
    "aspectRatio": "The computed aspect ratio derived from the aperture dimensions.",
    "magnification": "The magnification factor for orthographic projection.",
    "projectionType": "The projection type: PERSPECTIVE or ORTHOGRAPHIC.",
    # Light
    "lightType": "The type of light source: POINT, DIRECTIONAL, SPOT, AREA, or VOLUME.",
    # AnimationClip
    "description": "A human-readable description of this object.",
    "start": "The start time of the animation clip in seconds.",
    "stop": "The stop time of the animation clip in seconds.",
    "animations": "The animation nodes that drive scene-object properties within this clip.",
    # AnimationNode
    "bindPoints": "The list of bind points connecting scene-object properties to animation curves.",
    "subAnimations": "Nested animation nodes for hierarchical animation rigs.",
    # AnimationChannel
    "componentType": "The data type of the animated property component.",
    "defaultValue": "The default value used when no keyframe is active.",
    "keyframeSequence": "The keyframe sequence providing the animated values for this channel.",
    # BindPoint
    "property": "The scene-object property this bind point animates.",
    "channelsCount": "The number of animation channels registered on this bind point.",
    # KeyFrame
    "time": "The time position of this keyframe in seconds.",
    "value": "The scalar value at this keyframe.",
    "interpolation": "The interpolation method used between this keyframe and the next.",
    "tangentWeightMode": "Controls whether tangent weights are normalised or time-weighted.",
    "stepMode": "For CONSTANT interpolation, controls whether the current or next value is used.",
    "nextInTangent": "The incoming tangent vector at the next keyframe.",
    "outTangent": "The outgoing tangent vector at this keyframe.",
    "outWeight": "The weight of the outgoing tangent for weighted Bezier interpolation.",
    "nextInWeight": "The weight of the incoming tangent at the next keyframe.",
    "tension": "The tension parameter for TCB spline interpolation.",
    "continuity": "The continuity parameter for TCB spline interpolation.",
    "bias": "The bias parameter for TCB spline interpolation.",
    "independentTangent": "When true, incoming and outgoing tangents are controlled independently.",
    "flat": "When true, the tangent is forced horizontal (zero slope).",
    "timeIndependentTangent": "When true, tangent direction is not affected by time scaling.",
    "curve": "The parent keyframe sequence this keyframe belongs to.",
    # KeyframeSequence
    "bindPoint": "The bind point that this keyframe sequence is attached to.",
    "keyFrames": "The sorted list of keyframes in this animation curve.",
    "postBehavior": "The extrapolation behaviour applied after the last keyframe.",
    "preBehavior": "The extrapolation behaviour applied before the first keyframe.",
    # Extrapolation
    "type": "The extrapolation mode determining curve behaviour outside the keyframe range.",
    "repeatCount": "The number of repetitions for cycle-based extrapolation modes.",
    # BoundingBox
    "minimum": "The minimum corner of the bounding box.",
    "maximum": "The maximum corner of the bounding box.",
    "center": "The geometric centre of the bounding box.",
    "size": "The dimensions (width, height, depth) of the bounding box.",
    "extent": "The extent state of the bounding box (null, finite, or infinite).",
    # BoundingBoxExtent
    "extentX": "The extent value on the X axis.",
    "extentY": "The extent value on the Y axis.",
    "extentZ": "The extent value on the Z axis.",
    # IOConfig
    "fileFormat": "The file format to use for this I/O operation; null means auto-detect.",
    "encoding": "The text encoding used when reading or writing text-based formats.",
    "fileSystem": "The file system abstraction used to resolve external references such as textures.",
    "lookupPaths": "Additional search paths used when resolving relative file references.",
    "fileName": "The file name associated with this I/O operation.",
    # Property
    "valueType": "The type descriptor for the property value.",
    # PropertyCollection
    "count": "The number of properties in this collection.",
    "length": "The number of properties in this collection.",
    # Matrix4
    "determinant": "The determinant of this matrix.",
    "m00": "Matrix element at row 0, column 0.",
    "m01": "Matrix element at row 0, column 1.",
    "m02": "Matrix element at row 0, column 2.",
    "m03": "Matrix element at row 0, column 3.",
    "m10": "Matrix element at row 1, column 0.",
    "m11": "Matrix element at row 1, column 1.",
    "m12": "Matrix element at row 1, column 2.",
    "m13": "Matrix element at row 1, column 3.",
    "m20": "Matrix element at row 2, column 0.",
    "m21": "Matrix element at row 2, column 1.",
    "m22": "Matrix element at row 2, column 2.",
    "m23": "Matrix element at row 2, column 3.",
    "m30": "Matrix element at row 3, column 0.",
    "m31": "Matrix element at row 3, column 1.",
    "m32": "Matrix element at row 3, column 2.",
    "m33": "Matrix element at row 3, column 3.",
    "identity": "The 4×4 identity matrix (static property).",
    # Quaternion
    "w": "The scalar (real) component of the quaternion.",
    "x": "The x component.",
    "y": "The y component.",
    "z": "The z component.",
    # Vector2/Vector3/Vector4
    "length2": "The squared magnitude of this vector (avoids a square root).",
    # FbxElement
    "compound": "The first child element of this FBX element, or null.",
    "tokens": "The token objects contained in this FBX element.",
    "text": "The text content of this token.",
    # FbxProperty
    "name": "The name of this FBX property or element.",
    # FbxParser
    "rootScope": "The root FbxElement produced after parsing.",
    # FbxLoadOptions
    "keepBuiltinGlobalSettings": "When true, the FBX file's global settings node is preserved verbatim.",
    # FbxSaveOptions
    "embedTextures": "When true, texture image data is embedded in the FBX file.",
    # GltfLoadOptions
    "flipTexCoordV": "When true, vertically flips UV coordinates to match the target renderer's UV convention.",
    # GltfSaveOptions
    "binaryMode": "When true, writes a self-contained GLB binary container.",
    # GltfAccessor
    "bufferView": "Index of the GltfBufferView that contains this accessor's data.",
    "byteOffset": "Byte offset from the start of the buffer view to the first element.",
    "componentType": "The OpenGL component type code (e.g., 5126 for FLOAT).",
    "count": "The number of elements described by this accessor.",
    # GltfBufferView
    "buffer": "Index of the buffer this view references.",
    "byteLength": "Length in bytes of this buffer view.",
    "target": "The GPU buffer binding target.",
    "byteStride": "The byte stride between consecutive elements, or 0 for tightly packed.",
    # GltfNode
    "mesh": "Index of the mesh attached to this node, or -1 if none.",
    "children": "Indices of child nodes in the glTF node array.",
    # GltfPrimitive
    "attributes": "Map from attribute semantic name to accessor index.",
    "indices": "Accessor index for the index buffer, or -1 for non-indexed geometry.",
    "mode": "The OpenGL draw mode (e.g., 4 = TRIANGLES).",
    # GltfMaterial
    "pbrMetallicRoughness": "The PBR metallic-roughness parameters for this material.",
    "emissiveFactor": "The emissive colour as an [R, G, B] array.",
    "alphaMode": "The alpha blending mode: OPAQUE, MASK, or BLEND.",
    "alphaCutoff": "The alpha cutoff threshold used when alphaMode is MASK.",
    # GltfData
    "asset": "The glTF asset metadata object containing version and generator strings.",
    "scene": "The index of the default scene.",
    "scenes": "All scenes defined in the glTF document.",
    "accessors": "All accessors defined in the glTF document.",
    "bufferViews": "All buffer views defined in the glTF document.",
    "buffers": "All buffers defined in the glTF document.",
    "materials": "All materials defined in the glTF document.",
    # GltfMesh
    "primitives": "The list of primitives (draw calls) that make up this mesh.",
    # GltfScene
    "nodes": "Indices of root nodes in this scene.",
    # FbxFormat / ColladaFormat / etc.
    "extension": "The primary file extension for this format.",
    "extensions": "All file extensions recognised by this format.",
    "contentType": "The MIME content type string for this format.",
    "fileFormatType": "An internal type descriptor used to identify the format.",
    "version": "The format version string.",
    "canExport": "True if this format supports exporting.",
    "canImport": "True if this format supports importing.",
    "formats": "All format variants registered under this descriptor.",
    # GltfImporter
    "json": "The parsed GltfData tree from the imported glTF JSON.",
    "binary": "The binary buffer from the GLB container, or null for JSON-only glTF.",
    # TextureBase
    "content": "The raw image data or reference held by this texture.",
    # VertexDeclaration
    "sealed": "When true, the declaration is locked and no further fields can be added.",
    # VertexElementFVector
    "data": "The per-vertex or per-polygon-vertex data values.",
    # VertexElementUV
    "textureMapping": "The texture mapping slot this UV set corresponds to.",
    "uvData": "The UV coordinates as an array of FVector2 values.",
    # TransformBuilder
    "matrix": "The current accumulated transform matrix.",
    "composeOrder": "Controls whether new operations are appended or prepended.",
    # RelativeRectangle
    "scaleX": "The horizontal position scale factor relative to the parent rectangle.",
    "scaleY": "The vertical position scale factor relative to the parent rectangle.",
    "scaleWidth": "The width scale factor relative to the parent rectangle.",
    "scaleHeight": "The height scale factor relative to the parent rectangle.",
    "offsetX": "The horizontal pixel offset added after applying the scale.",
    "offsetY": "The vertical pixel offset added after applying the scale.",
    "offsetWidth": "The width pixel offset added after applying the scale.",
    "offsetHeight": "The height pixel offset added after applying the scale.",
    # Rect
    "left": "The x-coordinate of the left edge of the rectangle.",
    "right": "The x-coordinate of the right edge of the rectangle.",
    "top": "The y-coordinate of the top edge of the rectangle.",
    "bottom": "The y-coordinate of the bottom edge of the rectangle.",
    # BoundingBox2D
    # ColladaLoadOptions
    "flipCoordinateSystem": "When true, converts the coordinate system from the source format's convention.",
    "enableMaterials": "When true, material definitions are imported along with geometry.",
    "normalizeNormal": "When true, imported surface normals are normalised to unit length.",
    "scale": "A uniform scale factor applied to imported geometry.",
    # ColladaSaveOptions
    "indented": "When true, the XML output is indented for human readability.",
    # StlSaveOptions
    "binaryMode": "When true, writes binary output; when false, writes ASCII.",
    # ObjSaveOptions
    "applyUnitScale": "When true, applies the scene unit scale factor during export.",
    "pointCloud": "When true, exports only point positions without face connectivity.",
    "verbose": "When true, enables verbose logging during export.",
    "serializeW": "When true, includes the W component when writing normals.",
    "axisSystem": "Specifies the target axis system for coordinate conversion on export.",
    # ThreeMfSaveOptions
    "enableCompression": "When true, compresses the 3MF package contents.",
    "buildAll": "When true, all scene nodes are included in the 3MF build list.",
    "unit": "The length unit for the 3MF file (e.g., 'millimeter').",
    "prettyPrint": "When true, the XML inside the package is indented for human readability.",
    # FbxExporter
    "meshes": "The mesh objects collected from the scene during export.",
    # SemanticAttribute
    "semantic": "The vertex field semantic (e.g., POSITION, NORMAL, UV) for this attribute.",
    "alias": "An optional string alias for the attribute.",
    # VertexField
    "offset": "The byte offset of this field within one vertex record.",
    # ColladaImporter
    "effect": "The COLLADA effect name associated with the imported material.",
    # IIndexedVertexElement
    # VertexDeclaration
    "size": "The total size in bytes of one vertex record.",
    # FVector2
    # Extrapolation enum props already covered via EnumValues (see below)
    # LightType enum props
    "POINT": "An omnidirectional point light.",
    "DIRECTIONAL": "A directional light emitting parallel rays.",
    "SPOT": "A cone-shaped spot light.",
    "AREA": "A planar area light source.",
    "VOLUME": "A volumetric light source.",
    # ProjectionType
    "PERSPECTIVE": "Standard perspective projection with foreshortening.",
    "ORTHOGRAPHIC": "Parallel projection without depth distortion.",
    # ApertureMode
    "HORIZONTAL": "Field of view derived from the horizontal aperture size.",
    "VERTICAL": "Field of view derived from the vertical aperture size.",
    "HORZ_AND_VERT": "Field of view derived from both horizontal and vertical aperture sizes.",
    # RotationMode
    "FIXED": "The camera direction is fixed.",
    "ORBIT": "The camera orbits around its target point.",
    # BooleanOperation
    "ADD": "Computes the union of two meshes.",
    "SUB": "Subtracts one mesh from another.",
    "INTERSECT": "Computes the intersection of two meshes.",
    # SplitMeshPolicy
    "ADJUST": "Reindexes vertex element data when splitting a mesh by material.",
    "CLONE_DATA": "Duplicates vertex element data for each sub-mesh when splitting.",
    # MappingMode
    "CONTROL_POINT": "One data value per control point (vertex).",
    "POLYGON_VERTEX": "One data value per polygon corner.",
    "POLYGON": "One data value per polygon face.",
    "EDGE": "One data value per edge.",
    "ALL_SAME": "A single data value applied to all geometry elements.",
    # ReferenceMode
    "DIRECT": "Data values correspond directly to the mapping element indices.",
    "INDEX": "An explicit index array maps from mapping elements to data values.",
    "INDEX_TO_DIRECT": "An index array maps to data values stored in a direct array.",
    # ComposeOrder
    "APPEND": "Each new transform is post-multiplied.",
    "PREPEND": "Each new transform is pre-multiplied.",
    # VertexElementType
    "BINORMAL": "Binormal vector channel.",
    "NORMAL": "Surface normal vector channel.",
    "TANGENT": "Tangent vector channel.",
    "MATERIAL": "Per-polygon material index channel.",
    "POLYGON_GROUP": "Per-polygon group membership channel.",
    "UV": "UV texture coordinate channel.",
    "VERTEX_COLOR": "Per-vertex colour channel.",
    "SMOOTHING_GROUP": "Per-polygon smoothing group ID channel.",
    "VERTEX_CREASE": "Per-vertex crease weight for subdivision surface.",
    "EDGE_CREASE": "Per-edge crease weight for subdivision surface.",
    "USER_DATA": "Custom user-defined data channel.",
    "VISIBILITY": "Per-element visibility flag channel.",
    "SPECULAR": "Per-vertex specular intensity channel.",
    "WEIGHT": "Per-vertex skinning weight channel.",
    "HOLE": "Per-polygon hole flag channel.",
    # TextureMapping
    "AMBIENT": "UV set used for ambient colour texture.",
    "EMISSIVE": "UV set used for emissive texture.",
    "DIFFUSE": "UV set used for diffuse colour texture.",
    "OPACITY": "UV set used for opacity/transparency texture.",
    "BUMP": "UV set used for bump map texture.",
    "GLOW": "UV set used for glow texture.",
    "REFLECTION": "UV set used for reflection texture.",
    "SHADOW": "UV set used for shadow map projection.",
    "SHININESS": "UV set used for shininess (glossiness) texture.",
    "DISPLACEMENT": "UV set used for displacement map texture.",
    # WeightedMode
    "NONE": "Tangent weights are normalised; standard non-weighted Bezier interpolation.",
    "RIGHT": "The outgoing tangent has an explicit time weight.",
    "NEXT_LEFT": "The incoming tangent at the next keyframe has an explicit time weight.",
    "BOTH": "Both the outgoing and incoming tangents have explicit time weights.",
    # RotationOrder
    # Axis values already covered
    # ColladaImporter special
    "name": "The name identifying this object or element.",
    # FbxElement tokens text
    # ExtrapolationType / Interpolation enum values
    "CONSTANT": "Holds the boundary value; no change between keyframes.",
    "LINEAR": "Linear interpolation between keyframes.",
    "GRADIENT": "Linear extrapolation beyond the boundary using the tangent slope.",
    "CYCLE": "Repeats the animation from the beginning after each cycle.",
    "CYCLE_RELATIVE": "Repeats while accumulating the total value change each cycle.",
    "OSCILLATE": "Alternates the animation forward and backward (ping-pong).",
    "BEZIER": "Cubic Bezier interpolation using tangent handles.",
    "B_SPLINE": "B-spline interpolation for smooth curves.",
    "CARDINAL_SPLINE": "Cardinal spline interpolation with automatic tangents.",
    "TCB_SPLINE": "Tension-continuity-bias (Kochanek-Bartels) spline interpolation.",
    "PREVIOUS_VALUE": "Uses the current keyframe's value until the next keyframe is reached.",
    "NEXT_VALUE": "Jumps immediately to the next keyframe's value.",
    # VertexField
    "dataType": "The data type of this vertex field.",
    "index": "The multi-channel index for fields sharing the same semantic.",
}


def extract_method_name(cell0: str) -> str:
    """Get just the method name from a backtick-quoted signature."""
    # Remove backticks and get first token before (
    s = cell0.strip().strip('`').strip()
    return s.split('(')[0].strip()


def extract_prop_name(cell0: str) -> str:
    """Get just the property name from a backtick-quoted cell."""
    return cell0.strip().strip('`').strip()


def fill_empty_table_cells(content: str) -> str:
    lines = content.split('\n')
    result = []
    in_methods = False
    in_properties = False

    for line in lines:
        stripped = line.strip()

        if re.match(r'^## Methods', stripped):
            in_methods = True
            in_properties = False
        elif re.match(r'^## Properties', stripped):
            in_methods = False
            in_properties = True
        elif re.match(r'^## Constructors', stripped):
            in_methods = False
            in_properties = False
        elif re.match(r'^## ', stripped):
            in_methods = False
            in_properties = False

        # Only process table data rows (not header/separator rows)
        if (in_methods or in_properties) and stripped.startswith('|') and '|' in stripped[1:]:
            # Skip header and separator rows
            if re.match(r'^\|[\s\-:|]+\|', stripped):
                result.append(line)
                continue

            # Check if last cell is empty "  |" or just "|"
            if stripped.endswith('|  |') or stripped.endswith('| |'):
                parts = [p for p in line.split('|')]
                # Filter: parts[0] is indent, parts[-1] is '' (after last |)
                cells = parts[1:-1]  # actual cell content

                if in_methods and len(cells) >= 3:
                    sig_cell = cells[0].strip()
                    mname = extract_method_name(sig_cell)
                    desc = METHOD_DESCS.get(mname, "")
                    if desc:
                        cells[-1] = f" {desc} "
                        line = '|' + '|'.join(cells) + '|'

                elif in_properties and len(cells) >= 4:
                    name_cell = cells[0].strip()
                    pname = extract_prop_name(name_cell)
                    desc = PROP_DESCS.get(pname, "")
                    if desc:
                        cells[-1] = f" {desc} "
                        line = '|' + '|'.join(cells) + '|'

        result.append(line)
    return '\n'.join(result)


def process_file(path: Path) -> tuple[bool, str]:
    if path.name == '_index.md':
        return False, "skipped"
    content = path.read_text(encoding="utf-8")
    original = content
    content = fill_empty_table_cells(content)
    if content != original:
        path.write_text(content, encoding="utf-8")
        update_mechanism(path, "agent-edit")
        return True, "expanded"
    return False, "no changes"


def main():
    pages = sorted(REF_DIR.glob("*.md"))
    changed = 0
    unchanged = 0
    for page in pages:
        ok, reason = process_file(page)
        if ok:
            changed += 1
            print(f"  FILLED  {page.name}")
        else:
            unchanged += 1
    print(f"\nDone. Changed={changed}  Unchanged={unchanged}")


if __name__ == "__main__":
    main()
