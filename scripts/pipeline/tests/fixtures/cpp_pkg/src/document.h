// Fixture package: minimal C++ header exercising the declaration kinds
// tree_helpers._CLASS_TYPES["cpp"] / _FUNC_TYPES["cpp"] / _MODULE_TYPES["cpp"]
// are expected to handle (TC-MT040-40 declaration-kind census fixture).
#pragma once
#include <string>

namespace aspose {

// Base class -- reachability is Unknown-by-design for cpp (extraction/lang/
// cpp.py::export_surface always returns (None, None)), so every class here
// is expected to render regardless of a "reachable" field.
class Document {
public:
    Document();
    void Save(const std::string& path);
};

struct SaveOptions {
    bool compress;
};

enum class SaveFormat {
    Pdf,
    Docx
};

// Standalone top-level function (function_definition, not just a
// declaration) -- exercises _FUNC_TYPES["cpp"] == {"function_definition"}.
inline int ComputeChecksum(const std::string& data) {
    return static_cast<int>(data.size());
}

}  // namespace aspose
