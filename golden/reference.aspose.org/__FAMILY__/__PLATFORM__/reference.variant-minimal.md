<!-- GOLDEN REFERENCE | Platform-Bound: C# | Structural Exemplar | Original-Grade: B -->
---
linkTitle: "Class SplitPartInfo"
title: "Class SplitPartInfo"
description: "Represents the information of one input/output for multiple inputs/outputs, such as current page to be rendered when converting documents to image."
summary: "Represents the information of one input/output for multiple inputs/outputs, such as current page to be rendered when converting documents to image."
categories:
  - Class
layout: "reference-single"
grade: B
---

Namespace: [{{PRODUCT_FAMILY}}.LowCode](/{{PRODUCT_FAMILY}}/lowcode)
Assembly: {{PRODUCT_FAMILY}}.dll (26.2.0)

Represents the information of one input/output for multiple inputs/outputs,
such as current page to be rendered when converting documents to image.

```csharp
public class SplitPartInfo
```

#### Inheritance

[object](https://learn.microsoft.com/dotnet/api/system.object) ←
[SplitPartInfo](/{{PRODUCT_FAMILY}}/lowcode.splitpartinfo)

## Properties

The following properties are exposed by this class.

### <a id="SplitPartInfo_PartIndex"></a> PartIndex

Index of current part in sequence(0 based).
-1 means there are no multiple parts so the result is single.

```csharp
public int PartIndex { get; }
```

#### Property Value

 [int](https://learn.microsoft.com/dotnet/api/system.int32)

#### Remarks

If multiple sections need to be processed and every section is processed(split)
separately, the part index always starts from 0 for every section.
For example, when converting a document to images,
it represents the output page index of currently processed section.
And -1 denotes there is only one page for current section.

### <a id="SplitPartInfo_SectionIndex"></a> SectionIndex

Index of the section where current part is in. -1 denotes there is only one section.

```csharp
public int SectionIndex { get; }
```

#### Property Value

 [int](https://learn.microsoft.com/dotnet/api/system.int32)

### <a id="SplitPartInfo_SectionName"></a> SectionName

Name of the section where current part is in.

```csharp
public string SectionName { get; }
```

#### Property Value

 [string](https://learn.microsoft.com/dotnet/api/system.string)

#### Remarks

May be null for some situations, such as when rendering the whole document to tiff image.
