export { Document } from './document.js';
// TC-MT040-40: re-exported the same way 3d/typescript's real abstract base
// classes (Exporter, FileFormat, ...) are -- public API, barrel-reachable.
export { FormatHandler, ShapeKind } from './shapes.js';
