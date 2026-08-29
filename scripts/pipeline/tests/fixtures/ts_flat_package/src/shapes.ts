// TC-MT040-40 (D-1 declaration-kind census): this fixture originally only
// exercised class_declaration + function_declaration/method_definition
// (see document.ts/lexer.ts) -- it had NO abstract_class_declaration,
// interface_declaration, type_alias_declaration, enum_declaration or
// internal_module/module node anywhere, so a census run against it alone
// could never have proven abstract_class_declaration is a HANDLED kind (the
// exact gap G-TS-12 fixed in tree_helpers._CLASS_TYPES["typescript"]). This
// file adds one real declaration of each kind typescript's capability row
// claims to handle, mirroring 3d/typescript's real `export abstract class
// Exporter` shape (an abstract base re-exported from the package barrel).

/** Base class for save format handlers -- abstract_class_declaration. */
export abstract class FormatHandler {
  // No body -- abstract_method_signature, not method_signature (that node
  // type is reserved for interface/ambient bodies per tree_helpers.py's
  // TC-MT040-10 comment).
  abstract handle(name: string): void;
}

/** Options accepted by handle() -- interface_declaration. */
export interface HandleOptions {
  overwrite: boolean;
}

/** Alias for a handler name -- type_alias_declaration. */
export type HandlerName = string;

/** Recognized shapes -- enum_declaration. */
export enum ShapeKind {
  Circle,
  Square,
}

/** Grouping namespace (legacy `namespace` form) -- internal_module. */
export namespace Geometry {
  export function area(): number {
    return 0;
  }
}
