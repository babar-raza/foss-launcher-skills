function verifySavedDocument(path: string, sections: Section[]): void {
  const doc = Document.OpenFile(path);
  console.log('verifying saved document:');

  // 1. The flatten page is inert, while the AcroForm page's fields survive.
  const flatten = destPage(doc, 'section.flatten');
  check(flatten.GetText().includes('Annotation Flattening'),
    'the flattening page is present');
  check(flatten.Annotations.length === 0, 'the flattening page carries no /Annots');
  const names = doc.Form.Fields.map((f) => f.FullName);
  check(!names.includes('FlattenName') && !names.includes('FlattenCheck'),
    'the flattened fields are unwired from /AcroForm');
  check(names.includes('FullName') && names.includes('Plan'),
    "the AcroForm page's fields are still interactive");
  check(flatten.GetText().includes('Alice Sample'),
    'the flattened value is baked into page content');

  // 2. Applied redactions destroyed their values; unapplied marks did not.
  const redact = destPage(doc, 'section.redaction');
  check(redact.GetText().includes('Internal memo'), 'the redaction page is present');
  const redactText = redact.GetText();
  for (const v of REDACTED_VALUES) {
    check(!redactText.includes(v), `applied redaction destroyed ${JSON.stringify(v)}`);
  }
  for (const v of MARKED_VALUES) {
    check(redactText.includes(v), `unapplied mark preserved ${JSON.stringify(v)}`);
  }
  check(redact.Annotations.filter((a) => a.Subtype === 'Redact').length === 2,
    'two /Redact marks survive unapplied');

  // 3. Every navigation target resolves.
  const pageCount = doc.Pages.length;
  const destNames = new Set(doc.GetNamedDestinations().map((d) => d.name));
  for (const s of sections) {
    check(destNames.has(s.dest), `named destination ${s.dest} exists`);
  }
  for (const { name, dest } of doc.GetNamedDestinations()) {
    check(dest.page >= 1 && dest.page <= pageCount,
      `named destination ${name} targets a page in range`);
  }
  const walk = (items: OutlineItem[]): void => {
    for (const it of items) {
      if (it.Dest && isNamedDest(it.Dest)) {
        check(destNames.has(it.Dest.name),
          `outline "${it.Title}" names an existing destination`);
      }
      if (it.Children) walk(it.Children);
    }
  };
  walk(doc.GetOutlines());

  // 4. The barcode page drew every symbology.
  const barcode = destPage(doc, 'section.barcode');
  check(barcode.GetText().includes('Barcodes'), 'the barcode page is present');

  // Count subpaths, not paths: a vector barcode fills every module in ONE paint
  // op, so GetPaths() returns a handful of entries carrying hundreds of
  // subpaths each. Asserting on the path count would pass on a page that drew
  // nothing but its eight card frames.
  const barcodeSubpaths = barcode.GetPaths()
    .reduce((n, p) => n + p.subpaths.length, 0);
  check(barcodeSubpaths > 800,
    `the barcode page drew module geometry (${barcodeSubpaths} subpaths)`);

  const barcodeText = barcode.GetText();
  for (const payload of ['5901234123457', '036000291452', '96385074']) {
    check(barcodeText.includes(payload), `the human-readable payload ${payload} was drawn`);
  }

  // The raster QR is the page's only image: every other symbology is vector.
  let barcodeImages = 0;
  visitContent(doc, barcode, { image: () => { barcodeImages++; } });
  check(barcodeImages === 1,
    `render: 'raster' produced exactly one image XObject (${barcodeImages})`);

  // 5. Optional content: the layers, the nesting, and the default-off one.
  const oc = doc.OptionalContent;
  const layerNames = oc.Layers.map((l) => l.Name);
  for (const want of ['Walls', 'Furniture', 'Seating', 'Grid', 'Branding', 'Asset Tag']) {
    check(layerNames.includes(want), `layer "${want}" survives the save`);
  }
  const grid = oc.GetLayer('Grid');
  check(grid !== undefined && !oc.Default.IsVisible(grid),
    'the Grid layer is default-off in the /D config');
  const walls = oc.GetLayer('Walls');
  check(walls !== undefined && oc.Default.IsVisible(walls),
    'the Walls layer is default-on');

  // The panel tree: /D /Order represents nesting as an OCG followed by an array
  // of its children, so Seating must live in an array immediately after
  // Furniture. Layer *existence* alone would pass on a flat, unnested list.
  const order = doc.resolve(oc.Default.Dict.get('Order'));
  const seatingRef = oc.GetLayer('Seating')?.Ref;
  const furnitureRef = oc.GetLayer('Furniture')?.Ref;
  let nested = false;
  if (isArray(order) && seatingRef && furnitureRef) {
    for (let i = 0; i < order.length - 1; i++) {
      const here = order[i];
      const next = doc.resolve(order[i + 1]);
      if (isRef(here) && here.num === furnitureRef.num && isArray(next))
        nested = next.some((e) => isRef(e) && e.num === seatingRef.num);
    }
  }
  check(nested, 'Seating is nested under Furniture in /D /Order');

  // 6. The document is tagged, and the late-filled pages were hand-tagged.
  const tree = doc.GetStructTree();
  check(tree !== null, 'the s