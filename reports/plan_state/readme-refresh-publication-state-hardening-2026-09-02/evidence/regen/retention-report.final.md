# Retention report -- 3d/python

## Summary

- **content**: corrected=2, excluded=46, reframed=21, verbatim=17
- **structural**: excluded=2, reframed=1, verbatim=1
- **code**: api_survived=4, diagram=1, excluded=1, verbatim=17
- **badge**: verbatim=3
- **heading**: absent=8, absorbed=1, present=15

**Needs attention (8)**: heading:h0009, heading:h0011, heading:h0014, heading:h0015, heading:h0016, heading:h0017, heading:h0018, heading:h0019

## Prose content units (86)

| unit | old content | disposition | target | verdict | found in | fidelity / missing words |
|---|---|---|---|---|---|---|
| u0001 | Aspose.3D FOSS for Python is a free, open-source, pure-Python library for building, readin | merged_reframed | Intro | reframed | Intro (traced) | 0.73 (document) missing: cameras, compile, free, lights, models, moves, reading, writing |
| u0002 | - [At a glance](#at-a-glance) | merged_verbatim | Navigation | verbatim | Navigation | 1.0 (target_section) |
| u0003 | - [Key capabilities](#key-capabilities) | merged_verbatim | Navigation | verbatim | Navigation | 1.0 (target_section) |
| u0004 | - [Installation](#installation) | merged_verbatim | Navigation | verbatim | Navigation | 1.0 (target_section) |
| u0005 | - [Quick start](#quick-start) | merged_verbatim | Navigation | verbatim | Navigation | 1.0 (target_section) |
| u0006 | - [Additional examples](#additional-examples) | merged_verbatim | Navigation | verbatim | Navigation | 1.0 (target_section) |
| u0007 | - [API reference](#api-reference) | merged_verbatim | Navigation | verbatim | Navigation, Documentation & Resources | 1.0 (target_section) |
| u0008 | - [Documentation & resources](#documentation--resources) | merged_verbatim | Navigation | verbatim | Navigation | 1.0 (target_section) |
| u0009 | - [Scope and limitations](#scope-and-limitations) | merged_verbatim | Navigation | verbatim | Navigation | 1.0 (target_section) |
| u0010 | - [Development and testing](#development-and-testing) | merged_verbatim | Navigation | verbatim | Navigation, Dependencies | 1.0 (target_section) |
| u0011 | - [License](#license) | merged_verbatim | Navigation | verbatim | Navigation | 1.0 (target_section) |
| u0012 | - Build 3D scenes programmatically with `Scene`, `Node`, `Mesh`, `Camera`, and `Light` in  | merged_reframed | Key Capabilities | reframed | Key Capabilities (traced) | 0.6 (target_section) missing: camera, hierarchical, light, programmatically |
| u0013 | - Import OBJ (with `.mtl` materials), STL (binary and ASCII), glTF 2.0 / GLB, COLLADA (`.d | merged_reframed | Key Capabilities | reframed | Key Capabilities (traced) | 1.0 (document) |
| u0014 | - Export the same `Scene` model back out to OBJ, STL, glTF/GLB, or 3MF with `Scene.save(.. | merged_reframed | Key Capabilities | reframed | Key Capabilities (traced) | 0.67 (target_section) missing: currently, import, model, public, supported |
| u0015 | - Assign Lambert, Phong, or PBR (metallic-roughness) materials to nodes, including glTF ma | merged_reframed | Key Capabilities | reframed | Key Capabilities (traced) | 0.5 (target_section) missing: including, lambert, materials, metallic_factor, nodes, phong, roughness_factor |
| u0016 | - Convert built-in parametric primitives (`Box`, `Cylinder`, `Sphere`, `Torus`, `Pyramid`, | merged_reframed | Key Capabilities | reframed | Key Capabilities (traced) | 0.69 (target_section) missing: built, objects, parametric, triangulated |
| u0017 | - Work with `Vector2`/`Vector3`/`Vector4`, `Matrix4`, `Quaternion`, and `BoundingBox` util | excluded |  | excluded |  | 1.0 (document) |
| u0018 | - Animate scene properties with keyframe sequences (`AnimationClip`, `KeyframeSequence.add | merged_reframed | Key Capabilities | reframed | Key Capabilities (traced) | 0.53 (target_section) missing: animate, bindpoint, bound, interpolation, sequences, time, value |
| u0019 | A PyPI package has not been published yet. Install directly from a local clone: | corrected | Installation | corrected | Installation (traced) | 0.71 (target_section) missing: directly, local |
| u0020 | The package declares support for Python 3.7 through 3.12 and has no required third-party d | merged_reframed | Dependencies | reframed | Dependencies (traced) | 0.67 (target_section) missing: declares, support, through |
| u0021 | Load an OBJ scene and inspect its meshes: | merged_reframed | Quick Start | reframed | Quick Start (traced) | 0.5 (target_section) missing: load, meshes |
| u0022 | Convert the same kind of scene to a binary glTF (GLB): | merged_reframed | Additional Examples | reframed | Additional Examples (traced) | 0.6 (target_section) missing: binary, kind |
| u0023 | The snippets below cover building meshes from scratch, applying materials, and working wit | merged_reframed | Additional Examples | reframed | Additional Examples (traced) | 0.56 (target_section) missing: above, applying, building, cluttering, cover, meshes, scratch, working |
| u0024 | <details> <summary>View additional examples</summary> | merged_verbatim | Additional Examples | verbatim | Additional Examples | 1.0 (target_section) |
| u0025 | </details> | merged_verbatim | Additional Examples | verbatim | Additional Examples, API Reference | 1.0 (target_section) |
| u0026 | The public entry points are organized under `aspose.threed` (core scene graph), `aspose.th | merged_reframed | API Reference | reframed | API Reference (traced) | 0.73 (target_section) missing: cameras, classes, detection, documented, lights, live, math, move, organized, primitives, registry, submodules, threed |
| u0027 | > **Import from the format submodule, not the top-level package.** `aspose.threed.formats` | merged_reframed | Scope and Limitations | reframed | Scope and Limitations (traced) | 0.75 (document) missing: attributeerror, because, elsewhere, exports, fine, fully, ignore, inherit, init__, need, qualified, resolve, shown, stub |
| u0028 | <details> <summary>View the supported public API surface</summary> | merged_verbatim | API Reference | verbatim | API Reference | 1.0 (target_section) |
| u0029 | - `Scene` | excluded |  | excluded | __preamble__, API Reference | 1.0 (document) |
| u0030 | - `open(file_or_stream, options)`, `save(file_or_stream, format_or_options)`, `from_file(f | excluded |  | excluded |  | 0.57 (document) missing: file_or_stream, format_or_options, from_file |
| u0031 | - `root_node`, `sub_scenes`, `asset_info`, `animation_clips` | excluded |  | excluded |  | 0.25 (document) missing: animation_clips, asset_info, sub_scenes |
| u0032 | - `create_animation_clip(name)`, `clear()` | excluded |  | excluded |  | 0.33 (document) missing: clear, create_animation_clip |
| u0033 | - `Node` | excluded |  | excluded | __preamble__, API Reference | 1.0 (document) |
| u0034 | - `create_child_node(node_name, entity, material) -> 'Node'` | excluded |  | excluded |  | 0.8 (document) missing: node_name |
| u0035 | - `add_entity(entity)`, `add_child_node(node)`, `merge(node)` | excluded |  | excluded |  | 0.8 (document) missing: add_child_node |
| u0036 | - `entity`, `entities`, `material`, `materials`, `child_nodes`, `parent_node` | excluded |  | excluded |  | 0.83 (document) missing: parent_node |
| u0037 | - `transform`, `global_transform`, `visible`, `excluded` | excluded |  | excluded |  | 0.25 (document) missing: excluded, global_transform, visible |
| u0038 | - `evaluate_global_transform(with_geometric_transform)`, `get_bounding_box()` | excluded |  | excluded |  | 0.33 (document) missing: evaluate_global_transform, with_geometric_transform |
| u0039 | - `Entity` (base of `Mesh` and the primitive shapes) | excluded |  | excluded |  | 0.8 (document) missing: shapes |
| u0040 | - `get_bounding_box()`, `parent_node`, `parent_nodes`, `excluded`, `name` | excluded |  | excluded |  | 0.4 (document) missing: excluded, parent_node, parent_nodes |
| u0041 | - `Transform` / `GlobalTransform` | excluded |  | excluded |  | 1.0 (document) |
| u0042 | - `translation`, `scaling`, `rotation`, `euler_angles`, `transform_matrix` | excluded |  | excluded |  | 1.0 (document) |
| u0043 | - `set_translation(tx, ty, tz)`, `set_scale(sx, sy, sz)`, `set_rotation(rw, rx, ry, rz)` | excluded |  | excluded |  | 0.33 (document) missing: set_rotation, set_scale |
| u0044 | - `Mesh(name)` | excluded |  | excluded |  | 1.0 (document) |
| u0045 | - `control_points: ArrayListAdapter[Vector4]`, `polygon_count`, `polygons` | excluded |  | excluded |  | 1.0 (document) |
| u0046 | - `create_polygon(*indices)`, `triangulate()`, `get_bounding_box()` | excluded |  | excluded |  | 1.0 (document) |
| u0047 | - `Box`, `Cylinder`, `Sphere`, `Torus`, `Pyramid`, `Dish`, `Circle`, `Ellipse`, `Frustum` | excluded |  | excluded |  | 1.0 (document) |
| u0048 | - each exposes `to_mesh() -> 'Mesh'` to convert the parameterized primitive into a concret | excluded |  | excluded |  | 1.0 (document) |
| u0049 | - `Camera`, `Light` | excluded |  | excluded |  | 1.0 (document) |
| u0050 | - `near_plane`, `far_plane`, `field_of_view`, `direction`, `target`, `up` | excluded |  | excluded |  | 0.8 (document) missing: field_of_view |
| u0051 | - `Material` (base) — `get_texture(slot_name)`, `set_texture(slot_name, texture)` | excluded |  | excluded |  | 0.5 (document) missing: get_texture, set_texture, slot_name |
| u0052 | - `LambertMaterial` — `emissive_color`, `ambient_color`, `diffuse_color`, `transparent_col | excluded |  | excluded |  | 0.33 (document) missing: ambient_color, emissive_color, transparency, transparent_color |
| u0053 | - `PhongMaterial(LambertMaterial)` — adds `specular_color`, `specular_factor`, `shininess` | excluded |  | excluded |  | 0.57 (document) missing: reflection_color, shininess, specular_factor |
| u0054 | - `PbrMaterial` — `albedo`, `metallic_factor`, `roughness_factor`, `albedo_texture`, `norm | excluded |  | excluded |  | 0.44 (document) missing: albedo_texture, emissive_color, emissive_texture, normal_texture, occlusion_texture |
| u0055 | - `ObjLoadOptions` — `flip_coordinate_system`, `enable_materials`, `scale`, `normalize_nor | excluded |  | excluded |  | 0.8 (document) missing: normalize_normal |
| u0056 | - `ObjSaveOptions` — `apply_unit_scale`, `point_cloud`, `verbose`, `serialize_w`,   `enabl | excluded |  | excluded |  | 0.5 (document) missing: axis_system, point_cloud, serialize_w, verbose |
| u0057 | - `StlLoadOptions` / `StlSaveOptions` — `binary_mode` (save only), `scale`, `flip_coordina | excluded |  | excluded |  | 1.0 (document) |
| u0058 | - `GltfLoadOptions` / `GltfSaveOptions` — `binary_mode` (save only), `flip_tex_coord_v` | excluded |  | excluded |  | 1.0 (document) |
| u0059 | - `ColladaLoadOptions` / `ColladaSaveOptions` — `flip_coordinate_system`, `enable_material | excluded |  | excluded |  | 0.83 (document) missing: indented |
| u0060 | - `ThreeMfLoadOptions` / `ThreeMfSaveOptions` — `flip_coordinate_system`, `enable_compress | excluded |  | excluded |  | 0.75 (document) missing: build_all, pretty_print |
| u0061 | - `FbxLoadOptions` / `FbxSaveOptions` — `compatible_mode`, `export_textures`, `embed_textu | excluded |  | excluded |  | 1.0 (document) |
| u0062 | - `FileFormat` — `detect(stream, file_name)`, `get_format_by_extension(extension_name)`, ` | excluded |  | excluded |  | 0.62 (document) missing: can_export, can_import, extension_name |
| u0063 | - `Vector2`, `Vector3`, `Vector4` — `x`/`y`/`z`/`w`, `length`, `normalize()`, `dot()`, `cr | excluded |  | excluded |  | 1.0 (document) |
| u0064 | - `Matrix4` — `translate()`, `scale()`, `rotate()`, `decompose()`, `inverse()`, `get_ident | excluded |  | excluded |  | 0.43 (document) missing: decompose, inverse, rotate, translate |
| u0065 | - `Quaternion` — `slerp(t, v1, v2)`, `to_matrix()`, `from_euler_angle()`, `from_angle_axis | excluded |  | excluded |  | 0.4 (document) missing: from_angle_axis, from_euler_angle, to_matrix |
| u0066 | - `BoundingBox` — `minimum`, `maximum`, `center`, `size`, `merge()`, `contains()` | excluded |  | excluded |  | 0.71 (document) missing: maximum, minimum |
| u0067 | - `AnimationClip` — `create_animation_node(name) -> AnimationNode`, `animations`, `start`, | excluded |  | excluded |  | 0.86 (document) missing: stop |
| u0068 | - `AnimationNode` — `create_bind_point(obj, prop_name)`, `get_keyframe_sequence(target, pr | excluded |  | excluded |  | 0.33 (document) missing: bind_points, channel_name, create_bind_point, get_keyframe_sequence, prop_name, sub_animations |
| u0069 | - `AnimationChannel` (extends `KeyframeSequence`) — `component_type`, `default_value`,   ` | excluded |  | excluded |  | 0.5 (document) missing: default_value, extends, keyframe_sequence |
| u0070 | - `KeyframeSequence` — `add(time, value, interpolation)`, `key_frames`, `pre_behavior`/    | excluded |  | excluded |  | 0.62 (document) missing: key_frames, post_behavior, pre_behavior |
| u0071 | - `KeyFrame` — `time`, `value`, `interpolation` (`Interpolation`), tangent/weight fields   | excluded |  | excluded |  | 0.58 (document) missing: bias, continuity, step_mode, tangent_weight_mode, tension |
| u0072 | - `BindPoint`, `Interpolation`, `Extrapolation`/`ExtrapolationType`, `StepMode`, `Weighted | excluded |  | excluded |  | 1.0 (document) |
| u0073 | - `ImportException`, `ExportException`, `ParseException`, `InvalidOperationException` | excluded |  | excluded |  | 1.0 (document) |
| u0074 | </details> | merged_verbatim | API Reference | verbatim | Additional Examples, API Reference | 1.0 (target_section) |
| u0075 | - **[Getting started guide](https://docs.aspose.org/3d/python/)** — installation, key capa | merged_reframed | Documentation & Resources | reframed | Documentation & Resources (traced) | 0.71 (target_section) missing: capabilities, detailed, developer, links |
| u0076 | - **[How-to guides & FAQ](https://kb.aspose.org/3d/python/)** — task-focused how-to guides | merged_reframed | Documentation & Resources | reframed | Documentation & Resources (traced) | 0.58 (target_section) missing: converting, files, installable, loading, manipulating |
| u0077 | - **[Full API reference](https://reference.aspose.org/3d/python/)** — the complete, browsa | corrected | Documentation & Resources | corrected | Documentation & Resources (traced) | 1.0 (target_section) |
| u0078 | - Found a bug or have a feature request? [Open an issue](https://github.com/aspose-3d-foss | merged_verbatim | Documentation & Resources | verbatim | Documentation & Resources | 1.0 (target_section) |
| u0079 | This project focuses on scene-graph modeling and the OBJ, STL, glTF, COLLADA, and 3MF form | merged_reframed | Scope and Limitations | reframed | Scope and Limitations (traced) | 0.62 (target_section) missing: builds, curve, data, evaluation, focuses, graph, ibuffer, icommandlist, irenderwindow, itexture2d, modeling, pipelines, project, rasterize, reads, surface, writes |
| u0080 | FBX support is more limited than the other formats: the FBX tokenizer and parser are exerc | merged_reframed | Scope and Limitations | reframed | Scope and Limitations (traced) | 0.64 (target_section) missing: covered, exercised, fidelity, full, limited, matters, prefer, round, suite, trip |
| u0081 | COLLADA import works, but COLLADA export is not currently reachable through the public `Sc | merged_reframed | Scope and Limitations | reframed | Scope and Limitations (traced) | 0.68 (target_section) missing: ahead, currently, dispatcher, exists, implementation, plugin, reached, source, tree |
| u0082 | For workflows that need scene rendering, complete FBX read/write support, or additional fo | merged_reframed | Scope and Limitations | reframed | Scope and Limitations (traced) | 0.62 (target_section) missing: additional, complete, need, read, workflows, write |
| u0083 | Install the repository in editable mode and run the test suite: | merged_reframed | Development and Testing | reframed | Development and Testing (traced) | 0.67 (target_section) missing: editable, mode |
| u0084 | Run a single test file: | merged_verbatim | Development and Testing | verbatim | Development and Testing | 1.0 (target_section) |
| u0085 | The optional `dev` extra (`pip install -e ".[dev]"`) installs `pytest`, though the bundled | merged_reframed | Dependencies | reframed | Dependencies (traced) | 0.88 (target_section) missing: installs, though |
| u0086 | This project is licensed under the [MIT License](LICENSE). The MIT License permits use, co | merged_verbatim | License | verbatim | License | 1.0 (target_section) |

## Structural units (4)

| unit | old content | disposition | target | verdict | found in | fidelity / missing words |
|---|---|---|---|---|---|---|
| s0001 | At a glance (generic_structural_block) | merged_reframed | At a Glance | reframed |  |  |
| s0002 | Assign a PBR material and export to glTF (generic_structural_block) | merged_reframed | Additional Examples | verbatim | Additional Examples |  |
| s0003 | Import a COLLADA file (generic_structural_block) | excluded |  | excluded | Additional Examples |  |
| s0004 | Convert a parametric primitive to a mesh (generic_structural_block) | excluded |  | excluded |  |  |

## Code units (23)

| unit | old content | disposition | target | verdict | found in | fidelity / missing words |
|---|---|---|---|---|---|---|
| c0001 | [At a glance] flowchart TD | merged_reframed | At a Glance | diagram |  | 0/2 calls survive |
| c0002 | [Installation] git clone https://github.com/aspose-3d-foss/Aspose.3D-FOSS-for-Python.git | merged_reframed | Installation | api_survived | Installation | 1/2 calls survive |
| c0003 | [Quick start] scene = Scene() | merged_reframed | Quick Start | api_survived | Quick Start, Additional Examples | 3/3 calls survive |
| c0004 | [Quick start] scene = Scene() | merged_reframed | Additional Examples | api_survived | Quick Start, Additional Examples | 4/4 calls survive |
| c0005a | [Build a mesh and export it to STL] import io | merged_verbatim | Additional Examples | verbatim | Additional Examples |  |
| c0005b | [Build a mesh and export it to STL] scene = Scene() | merged_verbatim | Additional Examples | verbatim | Additional Examples | 5/5 calls survive |
| c0005c | [Build a mesh and export it to STL] node = scene.root_node.create_child_node("triangle_nod | merged_verbatim | Additional Examples | verbatim | Additional Examples | 1/1 calls survive |
| c0005d | [Build a mesh and export it to STL] stream = io.StringIO() | merged_verbatim | Additional Examples | verbatim | Additional Examples | 6/6 calls survive |
| c0006a | [Assign a PBR material and export to glTF] import io | merged_verbatim | Additional Examples | verbatim | Additional Examples |  |
| c0006b | [Assign a PBR material and export to glTF] scene = Scene() | merged_verbatim | Additional Examples | verbatim | Additional Examples | 5/5 calls survive |
| c0006c | [Assign a PBR material and export to glTF] albedo = Vector3(0.8, 0.2, 0.3) | merged_verbatim | Additional Examples | verbatim | Additional Examples | 2/2 calls survive |
| c0006d | [Assign a PBR material and export to glTF] node = scene.root_node.create_child_node("TestN | merged_verbatim | Additional Examples | verbatim | Additional Examples | 1/1 calls survive |
| c0006e | [Assign a PBR material and export to glTF] stream = io.BytesIO() | merged_verbatim | Additional Examples | verbatim | Additional Examples | 6/6 calls survive |
| c0006f | [Assign a PBR material and export to glTF] stream.seek(0) | merged_verbatim | Additional Examples | verbatim | Additional Examples | 4/4 calls survive |
| c0007 | [Import a COLLADA file] scene = Scene() | merged_verbatim | Additional Examples | verbatim | Additional Examples | 3/3 calls survive |
| c0008 | [Convert a parametric primitive to a mesh] box = Box(10, 20, 30) | excluded |  | excluded | Quick Start | 2/2 calls survive |
| c0009a | [Build a cube and export it to 3MF] import io | merged_verbatim | Additional Examples | verbatim | Additional Examples |  |
| c0009b | [Build a cube and export it to 3MF] scene = Scene() | merged_verbatim | Additional Examples | verbatim | Additional Examples | 4/4 calls survive |
| c0009c | [Build a cube and export it to 3MF] mesh.create_polygon(0, 1, 2) | merged_verbatim | Additional Examples | verbatim | Additional Examples | 1/1 calls survive |
| c0009d | [Build a cube and export it to 3MF] node = scene.root_node.create_child_node("cube") | merged_verbatim | Additional Examples | verbatim | Additional Examples | 1/1 calls survive |
| c0009e | [Build a cube and export it to 3MF] stream = io.BytesIO() | merged_verbatim | Additional Examples | verbatim | Additional Examples | 3/3 calls survive |
| c0010 | [Development and testing] git clone https://github.com/aspose-3d-foss/Aspose.3D-FOSS-for-P | merged_reframed | Development and Testing | api_survived | Installation | 1/2 calls survive |
| c0011 | [Development and testing] python -m unittest tests.test_obj_importer | merged_verbatim | Development and Testing | verbatim | Development and Testing |  |

## Badges (3)

| unit | old content | disposition | target | verdict | found in | fidelity / missing words |
|---|---|---|---|---|---|---|
| b0001 | License: MIT | preserved | __preamble__ | verbatim | __preamble__ |  |
| b0002 | Python | preserved | __preamble__ | verbatim | __preamble__ |  |
| b0003 | Contributors | preserved | __preamble__ | verbatim | __preamble__ |  |

## Headings (24)

| unit | old content | disposition | target | verdict | found in | fidelity / missing words |
|---|---|---|---|---|---|---|
| h0001 | # Aspose.3D FOSS for Python |  |  | present |  |  |
| h0002 | ## Navigation |  |  | present |  |  |
| h0003 | ## At a glance | structural_unit | s0001 | present |  |  |
| h0004 | ## Key capabilities |  |  | present |  |  |
| h0005 | ## Installation |  |  | present |  |  |
| h0006 | ## Quick start |  |  | present |  |  |
| h0007 | ## Additional examples |  |  | present |  |  |
| h0008 | ### Build a mesh and export it to STL |  |  | present |  |  |
| h0009 | ### Assign a PBR material and export to glTF | structural_unit | s0002 | absent |  |  |
| h0010 | ### Import a COLLADA file | structural_unit | s0003 | present |  |  |
| h0011 | ### Convert a parametric primitive to a mesh | structural_unit | s0004 | absent |  |  |
| h0012 | ### Build a cube and export it to 3MF |  |  | present |  |  |
| h0013 | ## API reference |  |  | present |  |  |
| h0014 | ### Scene graph (`aspose.threed`) |  |  | absent |  |  |
| h0015 | ### Meshes and primitives (`aspose.threed.entities`) |  |  | absent |  |  |
| h0016 | ### Materials (`aspose.threed.shading`) |  |  | absent |  |  |
| h0017 | ### Format load/save options (`aspose.threed.formats`) |  |  | absent |  |  |
| h0018 | ### Math utilities (`aspose.threed.utilities`) |  |  | absent |  |  |
| h0019 | ### Animation (`aspose.threed.animation`) |  |  | absent |  |  |
| h0020 | ### Exceptions |  |  | absorbed |  |  |
| h0021 | ## Documentation & resources |  |  | present |  |  |
| h0022 | ## Scope and limitations |  |  | present |  |  |
| h0023 | ## Development and testing |  |  | present |  |  |
| h0024 | ## License |  |  | present |  |  |
