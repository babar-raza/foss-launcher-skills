// Description:
// This sample applies supported non-rendering edits to layer metadata
// and saves the updated PSD/PSB document.

using Aspose.PSD;
using Aspose.PSD.FileFormats.Core.Blending;
using Aspose.PSD.FileFormats.Psd;
using Aspose.PSD.FileFormats.Psd.Layers;
using Aspose.PSD.FOSS.Samples.Common;

namespace Aspose.PSD.Samples.StructuralEditing;

/// <summary>
/// Hosts the structural editing sample entry point.
/// </summary>
internal static class Program
{
    /// <summary>
    /// Runs the structural editing sample.
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

        string outputPath = SamplePathHelper.ResolveOutputPath(args, 1, "structural-editing-sample-output.psd");
        RunStructuralEditing(inputPath, outputPath);
    }

    /// <summary>
    /// Loads a PSD or PSB file, applies supported structural edits, and saves the result.
    /// </summary>
    /// <param name="inputPath">The input PSD or PSB file path.</param>
    /// <param name="outputPath">The output PSD or PSB file path.</param>
    private static void RunStructuralEditing(string inputPath, string outputPath)
    {
        using var image = (PsdImage)Image.Load(inputPath);

        PrintSampleDescription(inputPath, outputPath, image.Layers.Length);

        if (image.Layers.Length == 0)
        {
            Console.WriteLine("The document has no layers, so no supported mutations were applied.");
            return;
        }

        Layer layer = image.Layers[0];
        Console.WriteLine("Before:");
        PrintEditableLayerState(layer);

        ApplySupportedEdits(layer);

        Console.WriteLine("After:");
        PrintEditableLayerState(layer);

        image.Save(outputPath);
        Console.WriteLine($"SavedEditedDocument: {outputPath}");
        SampleOutputHelper.OpenOutputFolder(outputPath);
    }

    /// <summary>
    /// Writes a short description of the sample and its current input/output files.
    /// </summary>
    /// <param name="inputPath">The input PSD or PSB file path.</param>
    /// <param name="outputPath">The output PSD or PSB file path.</param>
    /// <param name="layerCount">The parsed layer count.</param>
    private static void PrintSampleDescription(string inputPath, string outputPath, int layerCount)
    {
        Console.WriteLine("Aspose.PSD Structural Editing Sample");
        Console.WriteLine("Description: Applies supported non-rendering edits to layer metadata and saves the document.");
        Console.WriteLine($"Input: {inputPath}");
        Console.WriteLine($"Output: {outputPath}");
        Console.WriteLine($"LayerCount: {layerCount}");
        Console.WriteLine();
    }

    /// <summary>
    /// Applies the currently supported public edits to the first layer.
    /// </summary>
    /// <param name="layer">The target layer.</param>
    private static void ApplySupportedEdits(Layer layer)
    {
        layer.Name = $"{layer.Name} (edited)";
        layer.IsVisible = !layer.IsVisible;
        layer.Opacity = layer.Opacity == byte.MaxValue ? (byte)128 : byte.MaxValue;
        layer.Clipping = layer.Clipping == 0 ? (byte)1 : (byte)0;
        layer.BlendModeKey = layer.BlendModeKey == BlendMode.Normal ? BlendMode.Multiply : BlendMode.Normal;

        layer.Left += 1;
        layer.Top += 1;
        layer.Bottom += 1;
    }

    /// <summary>
    /// Prints the editable layer state that the sample mutates.
    /// </summary>
    /// <param name="layer">The layer to print.</param>
    private static void PrintEditableLayerState(Layer layer)
    {
        Console.WriteLine($"  Name: {layer.Name}");
        Console.WriteLine($"  IsVisible: {layer.IsVisible}");
        Console.WriteLine($"  Opacity: {layer.Opacity}");
        Console.WriteLine($"  Clipping: {layer.Clipping}");
        Console.WriteLine($"  BlendModeKey: {layer.BlendModeKey}");
        Console.WriteLine($"  Bounds: {layer.Bounds}");
        Console.WriteLine($"  Top: {layer.Top}");
        Console.WriteLine($"  Left: {layer.Left}");
        Console.WriteLine($"  Bottom: {layer.Bottom}");
        Console.WriteLine($"  Right: {layer.Right}");
        Console.WriteLine();
    }

    /// <summary>
    /// Prints usage instructions for the sample.
    /// </summary>
    private static void PrintUsage()
    {
        Console.WriteLine("Usage: dotnet run --project <sample-project> -- [input.psd] [output.psd]");
        Console.WriteLine("Description: Applies supported layer metadata edits and saves the result without any rendering pipeline.");
        Console.WriteLine("If no input path is provided, the sample tries to use the r