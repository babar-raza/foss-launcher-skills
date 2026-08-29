// TC-MT040-40: the legacy `module Foo {}` keyword form is a distinct
// top-level tree-sitter-typescript node type ("module") from the modern
// `namespace Foo {}` form ("internal_module") -- tree_helpers._MODULE_TYPES
// ["typescript"] declares both. Kept as its own tiny file so it never reads
// as a real recommended pattern next to shapes.ts's `namespace` example.
module LegacyGroup {
  export const marker = "legacy";
}
