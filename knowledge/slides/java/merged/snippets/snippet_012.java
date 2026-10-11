private static String describe(Element element) {
        StringBuilder text = new StringBuilder("<").append(element.getTagName());
        var attributes = element.getAttributes();
        for (int i = 0; i < attributes.getLength(); i++) {
            text.append(' ').append(attributes.item(i).getNodeName())
                    .append("=\"").append(attributes.item(i).getNodeValue()).append('"');
        }
        List<String> children = PackageAssertions.childNames(element);
        return children.isEmpty()
                ? text.append("/>").toString()
                : text.append('>').append(children).append("</").append(element.getTagName())
                .append('>').toString();
    }