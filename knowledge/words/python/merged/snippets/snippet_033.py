import aspose.words_foss as aw
from aspose.words_foss.saving import (
    MarkdownSaveOptions,
    OoxmlSaveOptions,
    PdfSaveOptions,
    CompressionLevel,
)

doc = aw.Document("input.docx")

# Markdown: underline, encoding, paragraph break
md_opts = MarkdownSaveOptions()
md_opts.export_underline_formatting = True
md_opts.encoding = "utf-8-sig"        # write a UTF-8 BOM
md_opts.paragraph_break = "\r\n"      # CRLF between paragraphs
doc.save("output.md", md_opts)

# DOCX: compression level
ooxml_opts = OoxmlSaveOptions()
ooxml_opts.compression_level = CompressionLevel.MAXIMUM
doc.save("output.docx", ooxml_opts)

pdf_opts = PdfSaveOptions()
doc.save("output.pdf", pdf_opts)
