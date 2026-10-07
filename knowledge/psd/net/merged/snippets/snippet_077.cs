protected static string SanitizePathSegment(string value)
    {
        char[] invalidCharacters = Path.GetInvalidFileNameChars();
        var builder = new System.Text.StringBuilder(value.Length);

        foreach (char character in value)
        {
            builder.Append(Array.IndexOf(invalidCharacters, character) >= 0 ? '_' : character);
        }

        return builder.ToString();
    }