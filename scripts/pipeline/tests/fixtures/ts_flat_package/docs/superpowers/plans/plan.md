# Planning doc

This is a planning document, not product documentation -- its fenced code
blocks describe a PROPOSED change, never real shipped product code, and must
never be harvested as a snippet (TC-MT040-16 negative control).

```ts
export function shouldNeverBeHarvested(): void {
  // if this ever shows up in snippets_index.json, the negative control failed
}
```
