internal static void OpenOutputFolder(string outputPath)
    {
        string fullOutputPath = Path.GetFullPath(outputPath);
        string outputDirectory = Path.GetDirectoryName(fullOutputPath) ?? Environment.CurrentDirectory;

        try
        {
            if (OperatingSystem.IsWindows())
            {
                Process.Start(new ProcessStartInfo
                {
                    FileName = "explorer",
                    Arguments = $"/select,\"{fullOutputPath}\"",
                    UseShellExecute = true
                });
            }
            else if (OperatingSystem.IsMacOS())
            {
                Process.Start(new ProcessStartInfo
                {
                    FileName = "open",
                    Arguments = $"-R \"{fullOutputPath}\"",
                    UseShellExecute = false
                });
            }
            else if (OperatingSystem.IsLinux())
            {
                Process.Start(new ProcessStartInfo
                {
                    FileName = "xdg-open",
                    Arguments = $"\"{outputDirectory}\"",
                    UseShellExecute = false
                });
            }

            Console.WriteLine($"OpenedOutputFolder: {outputDirectory}");
        }
        catch (Exception exception)
        {
            Console.WriteLine($"FailedToOpenOutputFolder: {exception.Message}");
        }
    }