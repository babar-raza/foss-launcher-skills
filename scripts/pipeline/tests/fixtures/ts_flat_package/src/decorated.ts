// TC-TSGAP-11 (2026-09-24, Seventh Pass of the pdf/typescript hardening
// plan): none of the 3 launched TS products (pdf/typescript, 3d/typescript,
// cells/typescript) use TC39-style decorators, so `decorator` had never
// been observed by the declaration-kind census and was absent from
// platform_capabilities.yaml's typescript.declared_ignored_kinds -- an
// unclassified-node-kind exposure for a future Angular/NestJS-flavored
// product. This file exercises both decorator positions (class-level,
// inside export_statement; member-level, inside class_body) so the census
// proves `decorator` is now correctly classified rather than merely
// asserted classified in the YAML.

/** Class-level decorator, mirroring `@Component(...)`. */
function ServiceDecorator(_target: Function): void {}

/** Member-level decorator, mirroring `@Input()`/`@HostListener(...)`. */
function TrackedDecorator(_target: unknown, _key: string): void {}

@ServiceDecorator
export class DecoratedService {
  @TrackedDecorator
  label: string = "";

  @TrackedDecorator
  run(): void {}
}
