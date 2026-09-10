private static List<String> slideTexts(PptxPackage pkg) throws IOException {
        List<String> texts = new ArrayList<>();
        for (Element sldId : PackageAssertions.selectNodes(
                pkg, "ppt/presentation.xml", "//p:sldIdLst/p:sldId")) {
            String relId = sldId.getAttributeNS(PptxPackage.NS_REL, "id");
            List<Element> rel = PackageAssertions.selectNodes(
                    pkg, "ppt/_rels/presentation.xml.rels",
                    "//rel:Relationship[@Id='" + relId + "']");
            String part = PptxPackage.resolveTarget(
                    "ppt/presentation.xml", rel.get(0).getAttribute("Target"));
            var text = new StringBuilder();
            for (Element t : PackageAssertions.selectNodes(pkg, part, "//a:t")) {
                text.append(t.getTextContent());
            }
            texts.add(text.toString());
        }
        return texts;
    }