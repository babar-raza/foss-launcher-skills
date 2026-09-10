private static void Enable(IEffectFormat format, string effect)
    {
        switch (effect)
        {
            case "Blur": format.EnableBlurEffect(); break;
            case "FillOverlay": format.EnableFillOverlayEffect(); break;
            case "Glow": format.EnableGlowEffect(); break;
            case "InnerShadow": format.EnableInnerShadowEffect(); break;
            case "OuterShadow": format.EnableOuterShadowEffect(); break;
            case "PresetShadow": format.EnablePresetShadowEffect(); break;
            case "Reflection": format.EnableReflectionEffect(); break;
            case "SoftEdge": format.EnableSoftEdgeEffect(); break;
            default: throw new ArgumentOutOfRangeException(nameof(effect), effect, "Unknown effect.");
        }
    }