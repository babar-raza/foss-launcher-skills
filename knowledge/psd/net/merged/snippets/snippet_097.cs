// Description:
// This sample demonstrates Load(Stream) and Save(Stream) by round-tripping
// a PSD/PSB document through in-memory streams without rendering.

using Aspose.PSD;
using Aspose.PSD.FileFormats.Psd;
using Aspose.PSD.FOSS.Samples.Common;

namespace Aspose.PSD.Samples.Streams;

/// <summary>
/// Hosts the stream round-trip sample entry point.
/// </summary>
internal static class Program
{
    /// <summary>
    /// Runs the stream round-trip sample.
    /// </summary>
    /// <param name="args">Optional command-line arguments: [input.psd] [output.psd].</param>
    private static void Main(string[] args)
    {
        string? inputPath = SamplePathHelper.ResolveInputPath(args);
        if (inputPath == null)
        {
            PrintUsage();
            return;
        }

        string outputPath = SamplePathHelper.ResolveOutputPath(args, 1, "streams-sample-output.psd");
        RunStreamRoundTrip(inputPath, outputPath);
    }

    /// <summary>
    /// Loads a PSD or PSB from an input stream and saves it to an output stream.
    /// </summary>
    /// <param name="inputPath">The input PSD or PSB file path.</param>
    /// <param name="outputPath">The output PSD or PSB file path.</param>
    private static void RunStreamRoundTrip(string inputPath, string outputPath)
    {
        byte[] inputBytes = File.ReadAllBytes(inputPath);

        using var inputStream = new MemoryStream(inputBytes);
        long originalPosition = inputStream.Position;
        using var image = (PsdImage)Image.Load(inputStream);

        PrintSampleDescription(inputPath, outputPath, inputBytes.Length, originalPosition, inputStream.Position);

        using var outputStream = new MemoryStream();
        image.Save(outputStream);
        File.WriteAllBytes(outputPath, outputStream.ToArray());

        Console.WriteLine($"SavedThroughStream: {outputPath}");
        Console.WriteLine($"OutputBytes: {outputStream.Length}");
        SampleOutputHelper.OpenOutputFolder(outputPath);
    }

    /// <summary>
    /// Writes a short description of the sample and its current stream state.
    /// </summary>
    /// <param name="inputPath">The input PSD or PSB file path.</param>
    /// <param name="outputPath">The output PSD or PSB file path.</param>
    /// <param name="inputByteCount">The byte count loaded into the input stream.</param>
    /// <param name="originalPosition">The input stream position before loading.</param>
    /// <param name="currentPosition">The input stream position after loading.</param>
    private static void PrintSampleDescription(
        string inputPath,
        string outputPath,
        int inputByteCount,
        long originalPosition,
        long currentPosition)
    {
        Console.WriteLine("Aspose.PSD Stream Sample");
        Console.WriteLine("Description: Demonstrates Load(Stream) and Save(Stream) using an in-memory round-trip without rendering.");
        Console.WriteLine($"Input: {inputPath}");
        Console.WriteLine($"Output: {outputPath}");
        Console.WriteLine($"InputBytes: {inputByteCount}");
        Console.WriteLine($"OriginalStreamPosition: {originalPosition}");
        Console.WriteLine($"StreamPositionAfterLoad: {currentPosition}");
        Console.WriteLine();
    }

    /// <summary>
    /// Prints usage instructions for the sample.
    /// </summary>
    private static void PrintUsage()
    {
        Console.WriteLine("Usage: dotnet run --project <sample-project> -- [input.psd] [output.psd]");
        Console.WriteLine("Description: Loads a PSD/PSB from a stream and saves it to another stream using an in-memory round-trip.");
        Console.WriteLine("If no input path is provided, the sample tries to use the repository test fixture.");
        Console.WriteLine("If no output path is provided, the sample writes to the repository tmp/ folder.");
    }
}
