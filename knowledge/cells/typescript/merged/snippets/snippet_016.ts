async function testHtmlImport() {
  console.log("Testing HTML import...");

  const html = `
<table>
  <thead>
    <tr><th>Name</th><th>Age</th></tr>
  </thead>
  <tbody>
    <tr><td>Alice</td><td>25</td></tr>
    <tr><td>Bob</td><td>30</td></tr>
  </tbody>
</table>
`;

  const doc = HtmlDocument.parse(html);
  console.log("Tables:", doc.tables.length);
  console.log("Rows:", doc.tables[0]?.rows);

  const workbook = doc.toWorkbook();
  console.log("Worksheets:", workbook.worksheets.length);
  console.log("A1:", workbook.worksheets[0]!.getCell(0, 0)?.value);
}