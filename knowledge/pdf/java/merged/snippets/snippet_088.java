private static String data(String... kv) {
        StringBuilder sb = new StringBuilder("<xfa:data xmlns:xfa='" + DATA + "'><form1>");
        for (int i = 0; i + 1 < kv.length; i += 2) {
            sb.append('<').append(kv[i]).append('>').append(kv[i + 1]).append("</").append(kv[i]).append('>');
        }
        return sb.append("</form1></xfa:data>").toString();
    }