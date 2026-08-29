const parts = doc.Split();                       // one Document per page
const chapter = doc.ExtractPages([3, 4, 5]);     // subset (1-based, repeats allowed) as a new Document
const merged = Document.Merge(docA, docB, docC); // new combined Document

docA.Append(docB);                               // copy all of docB's pages onto docA
docA.InsertPage(1, docB.Pages[0]);               // copy a single page across documents
