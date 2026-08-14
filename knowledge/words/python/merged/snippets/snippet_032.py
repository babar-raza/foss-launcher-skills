import io
import aspose.words_foss as aw

with io.FileIO("input.docx") as stream:
    doc = aw.Document(stream)              # DOCX / DOC / RTF from magic bytes

opts = aw.LoadOptions()
opts.load_format = aw.LoadFormat.MARKDOWN  # needed for .md, which has no magic bytes
with io.FileIO("input.md") as stream:
    doc = aw.Document(stream, opts)
