import io
import aspose.words_foss as aw

markdown_bytes = b"# Release Notes\n\nThis build adds **bold** and *italic* support.\n"

load_opts = aw.MarkdownLoadOptions()
doc = aw.Document(io.BytesIO(markdown_bytes), load_opts)
print(doc.get_text())

load_opts.preserve_empty_lines = True
doc = aw.Document(
    io.BytesIO(b"# Title\n\n\nParagraph after two blank lines.\n"), load_opts
)
