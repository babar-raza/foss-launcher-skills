const rest = page.AddTextBlock(longText, [72, 600, 200, 150], {
  font: 'Times-Roman', fontSize: 11, align: 'justify', valign: 'top', leading: 14,
});
if (rest) page.AddTextBlock(rest, [300, 600, 200, 150]); // continue into a 2nd column
