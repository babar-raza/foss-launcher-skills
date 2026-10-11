private static Arguments effect(String label, String tag, Consumer<IEffectFormat> enable,
                                    List<String> requiredAttributes,
                                    List<String> requiredChildGroup) {
        return Arguments.of(label, tag, enable, requiredAttributes, requiredChildGroup);
    }