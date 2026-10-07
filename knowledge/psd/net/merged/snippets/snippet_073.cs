public void Dispose()
    {
        try
        {
            Directory.Delete(_testDir, recursive: true);
        }
        catch
        {
        }
    }