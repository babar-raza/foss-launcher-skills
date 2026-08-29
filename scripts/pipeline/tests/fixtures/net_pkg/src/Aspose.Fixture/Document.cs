using System;

// Fixture package: minimal C# source exercising the declaration kinds
// tree_helpers._CLASS_TYPES["csharp"] / _FUNC_TYPES["csharp"] /
// _MODULE_TYPES["csharp"] are expected to handle (TC-MT040-40 declaration-kind
// census fixture). Platform "net" maps to tree-sitter language "csharp" via
// PLATFORM_TO_LANG.
namespace Aspose.Fixture
{
    /// <summary>Represents a document.</summary>
    public class Document
    {
        public Document() { }

        /// <summary>Save the document to the given path.</summary>
        public void Save(string path) { }

        public string Title { get; set; }
    }

    public interface IWriter
    {
        void Save(string path);
    }

    public enum SaveFormat
    {
        Pdf,
        Docx
    }

    public struct PageSize
    {
        public double Width;
        public double Height;
    }

    public record DocumentInfo(string Title, int PageCount);
}
