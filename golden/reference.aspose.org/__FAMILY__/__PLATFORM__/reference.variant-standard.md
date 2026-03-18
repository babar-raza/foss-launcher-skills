<!-- GOLDEN REFERENCE | Platform-Bound: C# | Structural Exemplar | Original-Grade: A -->
---
linkTitle: "Class SampleReader"
title: "Class SampleReader"
description: "SampleReader encapsulates a source which may contain one or several items, it then can perform ReadItems operation to detect items."
summary: "SampleReader encapsulates a source which may contain one or several items, it then can perform ReadItems operation to detect items."
categories:
  - Class
layout: "reference-single"
---

Namespace: [{{PRODUCT_FAMILY}}.Recognition](/{{PRODUCT_FAMILY}}/recognition)
Assembly: {{PRODUCT_FAMILY}}.dll (26.2.0)

SampleReader encapsulates a source which may contain one or several items, it then can perform ReadItems operation to detect items.

```csharp
public class SampleReader : IDisposable
```

#### Inheritance

[object](https://learn.microsoft.com/dotnet/api/system.object) ←
[SampleReader](/{{PRODUCT_FAMILY}}/recognition.samplereader)

#### Implements

[IDisposable](https://learn.microsoft.com/dotnet/api/system.idisposable)

#### Inherited Members

[object.GetType\(\)](https://learn.microsoft.com/dotnet/api/system.object.gettype),
[object.MemberwiseClone\(\)](https://learn.microsoft.com/dotnet/api/system.object.memberwiseclone),
[object.ToString\(\)](https://learn.microsoft.com/dotnet/api/system.object.tostring),
[object.Equals\(object?\)](https://learn.microsoft.com/dotnet/api/system.object.equals\#system\-object\-equals\(system\-object\)),
[object.Equals\(object?, object?\)](https://learn.microsoft.com/dotnet/api/system.object.equals\#system\-object\-equals\(system\-object\-system\-object\)),
[object.ReferenceEquals\(object?, object?\)](https://learn.microsoft.com/dotnet/api/system.object.referenceequals),
[object.GetHashCode\(\)](https://learn.microsoft.com/dotnet/api/system.object.gethashcode)

## Examples

This sample shows how to detect TypeA and TypeB items.

```csharp
using (SampleReader reader = new SampleReader(@"c:\test.png", DecodeType.TypeA, DecodeType.TypeB))
{
    foreach (ReadResult result in reader.ReadItems())
    {
        Console.WriteLine("Item Type: " + result.TypeName);
        Console.WriteLine("Item Text: " + result.Text);
    }
}
```

## Constructors

The following constructors are available for creating instances of this class.

### <a id="SampleReader__ctor"></a> SampleReader\(\)

Initializes a new instance of the SampleReader class with default values.
Requires to set source (SetSourceImage()) before to call ReadItems() method.

```csharp
public SampleReader()
```

#### Examples

This sample shows how to detect TypeA and TypeB items.

```csharp
using (SampleReader reader = new SampleReader())
{
    reader.SetReadType(DecodeType.TypeA, DecodeType.TypeB);
    reader.SetSourceImage(@"c:\test.png");
    foreach (ReadResult result in reader.ReadItems())
    {
        Console.WriteLine("Item Type: " + result.TypeName);
        Console.WriteLine("Item Text: " + result.Text);
    }
}
```

### <a id="SampleReader__ctor_Bitmap_"></a> SampleReader\(Bitmap\)

```csharp
public SampleReader(Bitmap image)
```

#### Parameters

`image` Bitmap

### <a id="SampleReader__ctor_Bitmap_BaseDecodeType___"></a> SampleReader\(Bitmap, params BaseDecodeType\[\]\)

```csharp
public SampleReader(Bitmap image, params BaseDecodeType[] decodeTypes)
```

#### Parameters

`image` Bitmap

`decodeTypes` [BaseDecodeType](/{{PRODUCT_FAMILY}}/recognition.basedecodetype)\[\]

### <a id="SampleReader__ctor_Bitmap_BaseDecodeType_"></a> SampleReader\(Bitmap, BaseDecodeType\)

```csharp
public SampleReader(Bitmap image, BaseDecodeType type)
```

#### Parameters

`image` Bitmap

`type` [BaseDecodeType](/{{PRODUCT_FAMILY}}/recognition.basedecodetype)

### <a id="SampleReader__ctor_Bitmap_Rectangle_BaseDecodeType___"></a> SampleReader\(Bitmap, Rectangle, params BaseDecodeType\[\]\)

```csharp
public SampleReader(Bitmap image, Rectangle area, params BaseDecodeType[] decodeTypes)
```

#### Parameters

`image` Bitmap

`area` Rectangle

`decodeTypes` [BaseDecodeType](/{{PRODUCT_FAMILY}}/recognition.basedecodetype)\[\]

### <a id="SampleReader__ctor_Bitmap_Rectangle_BaseDecodeType_"></a> SampleReader\(Bitmap, Rectangle, BaseDecodeType\)

```csharp
public SampleReader(Bitmap image, Rectangle area, BaseDecodeType type)
```

#### Parameters

`image` Bitmap

`area` Rectangle

`type` [BaseDecodeType](/{{PRODUCT_FAMILY}}/recognition.basedecodetype)

### <a id="SampleReader__ctor_Bitmap_Rectangle___BaseDecodeType___"></a> SampleReader\(Bitmap, Rectangle\[\], params BaseDecodeType\[\]\)

```csharp
public SampleReader(Bitmap image, Rectangle[] areas, params BaseDecodeType[] decodeTypes)
```

#### Parameters

`image` Bitmap

`areas` Rectangle\[\]

`decodeTypes` [BaseDecodeType](/{{PRODUCT_FAMILY}}/recognition.basedecodetype)\[\]

### <a id="SampleReader__ctor_Bitmap_Rectangle___BaseDecodeType_"></a> SampleReader\(Bitmap, Rectangle\[\], BaseDecodeType\)

```csharp
public SampleReader(Bitmap image, Rectangle[] areas, BaseDecodeType type)
```

#### Parameters

`image` Bitmap

`areas` Rectangle\[\]

`type` [BaseDecodeType](/{{PRODUCT_FAMILY}}/recognition.basedecodetype)

### <a id="SampleReader__ctor_string_"></a> SampleReader\(string\)

Initializes a new instance of the SampleReader class from file.

```csharp
public SampleReader(string filename)
```

#### Parameters

`filename` [string](https://learn.microsoft.com/dotnet/api/system.string)

The filename.

#### Examples

This sample shows how to detect TypeA and TypeB items.

```csharp
using (SampleReader reader = new SampleReader(@"c:\test.png"))
{
    reader.SetReadType(DecodeType.TypeA, DecodeType.TypeB);
    foreach (ReadResult result in reader.ReadItems())
    {
        Console.WriteLine("Item Type: " + result.TypeName);
        Console.WriteLine("Item Text: " + result.Text);
    }
}
```

### <a id="SampleReader__ctor_string_BaseDecodeType___"></a> SampleReader\(string, params BaseDecodeType\[\]\)

Initializes a new instance of the SampleReader class.

```csharp
public SampleReader(string filename, params BaseDecodeType[] decodeTypes)
```

#### Parameters

`filename` [string](https://learn.microsoft.com/dotnet/api/system.string)

The filename.

`decodeTypes` [BaseDecodeType](/{{PRODUCT_FAMILY}}/recognition.basedecodetype)\[\]

Decode types.

#### Examples

This sample shows how to detect TypeA and TypeB items.

```csharp
using (SampleReader reader = new SampleReader(@"c:\test.png", DecodeType.TypeA, DecodeType.TypeB))
{
    foreach (ReadResult result in reader.ReadItems())
    {
        Console.WriteLine("Item Type: " + result.TypeName);
        Console.WriteLine("Item Text: " + result.Text);
    }
}
```

### <a id="SampleReader__ctor_string_BaseDecodeType_"></a> SampleReader\(string, BaseDecodeType\)

Initializes a new instance of the SampleReader class.

```csharp
public SampleReader(string filename, BaseDecodeType type)
```

#### Parameters

`filename` [string](https://learn.microsoft.com/dotnet/api/system.string)

The filename.

`type` [BaseDecodeType](/{{PRODUCT_FAMILY}}/recognition.basedecodetype)

The decode type.

#### Examples

This sample shows how to detect TypeA and TypeB items.

```csharp
using (SampleReader reader = new SampleReader(@"c:\test.png", new MultiDecodeType(DecodeType.TypeA, DecodeType.TypeB)))
{
    foreach (ReadResult result in reader.ReadItems())
    {
        Console.WriteLine("Item Type: " + result.TypeName);
        Console.WriteLine("Item Text: " + result.Text);
    }
}
```

### <a id="SampleReader__ctor_Stream_"></a> SampleReader\(Stream\)

Initializes a new instance of the SampleReader class.

```csharp
public SampleReader(Stream stream)
```

#### Parameters

`stream` [Stream](https://learn.microsoft.com/dotnet/api/system.io.stream)

The stream.

#### Examples

This sample shows how to detect TypeA and TypeB items.

```csharp
using (FileStream fstr = new FileStream(@"c:\test.png", FileMode.Open))
using (SampleReader reader = new SampleReader(fstr))
{
    reader.SetReadType(DecodeType.TypeA, DecodeType.TypeB);
    foreach (ReadResult result in reader.ReadItems())
    {
        Console.WriteLine("Item Type: " + result.TypeName);
        Console.WriteLine("Item Text: " + result.Text);
    }
}
```

### <a id="SampleReader__ctor_Stream_BaseDecodeType_"></a> SampleReader\(Stream, BaseDecodeType\)

Initializes a new instance of the SampleReader class.

```csharp
public SampleReader(Stream stream, BaseDecodeType type)
```

#### Parameters

`stream` [Stream](https://learn.microsoft.com/dotnet/api/system.io.stream)

The stream.

`type` [BaseDecodeType](/{{PRODUCT_FAMILY}}/recognition.basedecodetype)

The decode type.

#### Examples

This sample shows how to detect TypeA and TypeB items.

```csharp
using (FileStream fstr = new FileStream(@"c:\test.png", FileMode.Open))
using (SampleReader reader = new SampleReader(fstr, new MultiDecodeType(DecodeType.TypeA, DecodeType.TypeB)))
{
    foreach (ReadResult result in reader.ReadItems())
    {
        Console.WriteLine("Item Type: " + result.TypeName);
        Console.WriteLine("Item Text: " + result.Text);
    }
}
```

### <a id="SampleReader__ctor_Stream_BaseDecodeType___"></a> SampleReader\(Stream, params BaseDecodeType\[\]\)

Initializes a new instance of the SampleReader class.

```csharp
public SampleReader(Stream stream, params BaseDecodeType[] decodeTypes)
```

#### Parameters

`stream` [Stream](https://learn.microsoft.com/dotnet/api/system.io.stream)

The stream.

`decodeTypes` [BaseDecodeType](/{{PRODUCT_FAMILY}}/recognition.basedecodetype)\[\]

Decode types.

#### Examples

This sample shows how to detect TypeA and TypeB items.

```csharp
using (FileStream fstr = new FileStream(@"c:\test.png", FileMode.Open))
using (SampleReader reader = new SampleReader(fstr, DecodeType.TypeA, DecodeType.TypeB))
{
    foreach (ReadResult result in reader.ReadItems())
    {
        Console.WriteLine("Item Type: " + result.TypeName);
        Console.WriteLine("Item Text: " + result.Text);
    }
}
```

## Properties

The following properties are exposed by this class for configuring and inspecting its state.

### <a id="SampleReader_ReadType"></a> ReadType

Gets or sets the decode type used for recognition.
Must be set before calling ReadItems.

```csharp
public BaseDecodeType ReadType { get; set; }
```

#### Property Value

 [BaseDecodeType](/{{PRODUCT_FAMILY}}/recognition.basedecodetype)

#### Examples

This sample shows how to detect TypeA and TypeB items.

```csharp
using (SampleReader reader = new SampleReader())
{
    reader.ReadType = new MultiDecodeType(DecodeType.TypeA, DecodeType.TypeB);
    reader.SetSourceImage(@"c:\test.png");
    foreach (ReadResult result in reader.ReadItems())
    {
        Console.WriteLine("Item Type: " + result.TypeName);
        Console.WriteLine("Item Text: " + result.Text);
    }
    Console.WriteLine("ReadType: " + reader.ReadType.ToString());
}
```

### <a id="SampleReader_Settings"></a> Settings

The main decoding parameters. Contains parameters which make influence on recognized data.

```csharp
public ReaderSettings Settings { get; }
```

#### Property Value

 [ReaderSettings](/{{PRODUCT_FAMILY}}/recognition.readersettings)

### <a id="SampleReader_FoundItems"></a> FoundItems

Gets recognized ReadResult array

```csharp
public ReadResult[] FoundItems { get; }
```

#### Property Value

 [ReadResult](/{{PRODUCT_FAMILY}}/recognition.readresult)\[\]

#### Examples

This sample shows how to read items with SampleReader

```csharp
using (SampleReader reader = new SampleReader(@"c:\test.png", DecodeType.TypeA, DecodeType.TypeB))
{
    reader.ReadItems();
    for(int i = 0; reader.FoundCount > i; ++i)
        Console.WriteLine("Item Text: " + reader.FoundItems[i].Text);
}
```

### <a id="SampleReader_FoundCount"></a> FoundCount

Gets recognized items count

```csharp
public int FoundCount { get; }
```

#### Property Value

 [int](https://learn.microsoft.com/dotnet/api/system.int32)

#### Examples

This sample shows how to read items with SampleReader

```csharp
using (SampleReader reader = new SampleReader(@"c:\test.png", DecodeType.TypeA, DecodeType.TypeB))
{
    reader.ReadItems();
    for(int i = 0; reader.FoundCount > i; ++i)
        Console.WriteLine("Item Text: " + reader.FoundItems[i].Text);
}
```

### <a id="SampleReader_ProcessorSettings"></a> ProcessorSettings

Gets a settings of using processor cores.

```csharp
public static ProcessorSettings ProcessorSettings { get; }
```

#### Property Value

 [ProcessorSettings](/{{PRODUCT_FAMILY}}/common.processorsettings)

#### Examples

This sample shows how to use ProcessorSettings to add maximum multi-threaded performance

```csharp
//this allows to use all cores for single SampleReader call
SampleReader.ProcessorSettings.UseAllCores = true;
//this allows to use current count of cores
SampleReader.ProcessorSettings.UseAllCores = false;
SampleReader.ProcessorSettings.UseOnlyThisCoresCount = Math.Max(1, Environment.ProcessorCount / 2);
```

### <a id="SampleReader_QualitySettings"></a> QualitySettings

QualitySettings allows to configure recognition quality and speed manually.
You can quickly set up QualitySettings by embedded presets: HighPerformance, NormalQuality,
HighQuality, MaxItems or you can manually configure separate options.
Default value of QualitySettings is NormalQuality.

```csharp
public QualitySettings QualitySettings { get; set; }
```

#### Property Value

 [QualitySettings](/{{PRODUCT_FAMILY}}/recognition.qualitysettings)

#### Examples

This sample shows how to use QualitySettings with SampleReader

```csharp
using (SampleReader reader = new SampleReader(@"c:\test.png", DecodeType.TypeA, DecodeType.TypeB))
{
   //set high performance mode
   reader.QualitySettings = QualitySettings.HighPerformance;
   foreach (ReadResult result in reader.ReadItems())
      Console.WriteLine("Item Text: " + result.Text);
}
using (SampleReader reader = new SampleReader(@"c:\test.png", DecodeType.TypeA, DecodeType.TypeB))
{
   //normal quality mode is set by default
   foreach (ReadResult result in reader.ReadItems())
      Console.WriteLine("Item Text: " + result.Text);
}
using (SampleReader reader = new SampleReader(@"c:\test.png", DecodeType.TypeA, DecodeType.TypeB))
{
   //set high performance mode
   reader.QualitySettings = QualitySettings.HighPerformance;
   //set separate options
   reader.QualitySettings.AllowMedianSmoothing = true;
   reader.QualitySettings.MedianSmoothingWindowSize = 5;
   foreach (ReadResult result in reader.ReadItems())
      Console.WriteLine("Item Text: " + result.Text);
}
```

### <a id="SampleReader_Timeout"></a> Timeout

Gets or sets the timeout of recognition process in milliseconds.

```csharp
public int Timeout { get; set; }
```

#### Property Value

 [int](https://learn.microsoft.com/dotnet/api/system.int32)

#### Examples

This sample shows how to avoid recognition hangs with timeout on large inputs

```csharp
using (SampleReader reader = new SampleReader(@"c:\test.png"))
{
    reader.Timeout = 5000;
    foreach (ReadResult result in reader.ReadItems())
        Console.WriteLine("Item Text: " + result.Text);
}
```

## Methods

The following methods are available for performing operations with this class.

### <a id="SampleReader_Abort"></a> Abort\(\)

Function requests termination of current recognition session from other thread. Abort is unblockable method and returns control just after calling.
The method should be used when recognition process is too long.

```csharp
public void Abort()
```

#### Examples

This sample shows how to call Abort function from other thread

```csharp
private static void ThreadRecognize(object readerObj)
{
    SampleReader reader = (SampleReader)readerObj;
    foreach (ReadResult result in reader.ReadItems())
    {
        Console.WriteLine("Item Type: " + result.TypeName);
        Console.WriteLine("Item Text: " + result.Text);
    }
}

SampleReader reader = new SampleReader(@"c:\test.png", DecodeType.TypeA, DecodeType.TypeB);
Thread thread1 = new Thread(ThreadRecognize);
thread1.Start(reader);
Thread.Sleep(100);
reader.Abort();
```

### <a id="SampleReader_Dispose"></a> Dispose\(\)

```csharp
public void Dispose()
```

### <a id="SampleReader_ExportToXml_string_"></a> ExportToXml\(string\)

Exports properties to the xml-file specified

```csharp
public bool ExportToXml(string xmlFile)
```

#### Parameters

`xmlFile` [string](https://learn.microsoft.com/dotnet/api/system.string)

The name for the file

#### Returns

 [bool](https://learn.microsoft.com/dotnet/api/system.boolean)

Whether or not export completed successfully.
            <p>Returns <b>True</b> in case of success; <b>False</b> Otherwise </p>

### <a id="SampleReader_ExportToXml_Stream_"></a> ExportToXml\(Stream\)

Exports properties to the xml-stream specified

```csharp
public bool ExportToXml(Stream xmlStream)
```

#### Parameters

`xmlStream` [Stream](https://learn.microsoft.com/dotnet/api/system.io.stream)

The xml-stream for saving

#### Returns

 [bool](https://learn.microsoft.com/dotnet/api/system.boolean)

Whether or not export completed successfully.
            <p>Returns <b>True</b> in case of success; <b>False</b> Otherwise </p>

### <a id="SampleReader_ImportFromXml_string_"></a> ImportFromXml\(string\)

Imports properties from the xml-file specified and applies them to the current SampleReader instance.

```csharp
public static SampleReader ImportFromXml(string xmlFile)
```

#### Parameters

`xmlFile` [string](https://learn.microsoft.com/dotnet/api/system.string)

The name for the file

#### Returns

 [SampleReader](/{{PRODUCT_FAMILY}}/recognition.samplereader)

Returns <b>True</b> in case of success; <p><b>False</b> Otherwise </p>

### <a id="SampleReader_ImportFromXml_Stream_"></a> ImportFromXml\(Stream\)

Imports properties from the xml-stream specified and applies them to the current SampleReader instance.

```csharp
public static SampleReader ImportFromXml(Stream xmlStream)
```

#### Parameters

`xmlStream` [Stream](https://learn.microsoft.com/dotnet/api/system.io.stream)

The xml-stream for loading

#### Returns

 [SampleReader](/{{PRODUCT_FAMILY}}/recognition.samplereader)

Returns <b>True</b> in case of success; <p><b>False</b> Otherwise </p>

### <a id="SampleReader_ReadItems"></a> ReadItems\(\)

Reads ReadResults from the source.

```csharp
public ReadResult[] ReadItems()
```

#### Returns

 [ReadResult](/{{PRODUCT_FAMILY}}/recognition.readresult)\[\]

Returns array of recognized ReadResults. If nothing is recognized, zero array is returned.

#### Examples

This sample shows how to read items with SampleReader

```csharp
using (SampleReader reader = new SampleReader(@"c:\test.png", DecodeType.TypeA, DecodeType.TypeB))
{
    foreach (ReadResult result in reader.ReadItems())
        Console.WriteLine("Item Text: " + result.Text);
}
using (SampleReader reader = new SampleReader(@"c:\test.png", DecodeType.TypeA, DecodeType.TypeB))
{
    reader.ReadItems();
    for(int i = 0; reader.FoundCount > i; ++i)
        Console.WriteLine("Item Text: " + reader.FoundItems[i].Text);
}
```

### <a id="SampleReader_SetSourceImage_Bitmap_"></a> SetSourceImage\(Bitmap\)

```csharp
public void SetSourceImage(Bitmap value)
```

#### Parameters

`value` Bitmap

### <a id="SampleReader_SetSourceImage_Bitmap_Rectangle___"></a> SetSourceImage\(Bitmap, Rectangle\[\]\)

```csharp
public void SetSourceImage(Bitmap value, Rectangle[] areas)
```

#### Parameters

`value` Bitmap

`areas` Rectangle\[\]

### <a id="SampleReader_SetSourceImage_Bitmap_Rectangle_"></a> SetSourceImage\(Bitmap, Rectangle\)

```csharp
public void SetSourceImage(Bitmap value, Rectangle area)
```

#### Parameters

`value` Bitmap

`area` Rectangle

### <a id="SampleReader_SetSourceImage_string_"></a> SetSourceImage\(string\)

Sets image file for recognition.
Must be called before ReadItems() method.

```csharp
public void SetSourceImage(string filename)
```

#### Parameters

`filename` [string](https://learn.microsoft.com/dotnet/api/system.string)

The image file for recognition.

#### Examples

This sample shows how to detect TypeA and TypeB items.

```csharp
using (SampleReader reader = new SampleReader())
{
    reader.SetReadType(DecodeType.TypeA, DecodeType.TypeB);
    reader.SetSourceImage(@"c:\test.png");
    foreach (ReadResult result in reader.ReadItems())
    {
        Console.WriteLine("Item Type: " + result.TypeName);
        Console.WriteLine("Item Text: " + result.Text);
    }
}
```

### <a id="SampleReader_SetSourceImage_Stream_"></a> SetSourceImage\(Stream\)

Sets image stream for recognition.
Must be called before ReadItems() method.

```csharp
public void SetSourceImage(Stream stream)
```

#### Parameters

`stream` [Stream](https://learn.microsoft.com/dotnet/api/system.io.stream)

The image stream for recognition.

#### Examples

This sample shows how to detect TypeA and TypeB items.

```csharp
using (FileStream fstr = new FileStream(@"c:\test.png", FileMode.Open))
using (SampleReader reader = new SampleReader())
{
    reader.SetReadType(DecodeType.TypeA, DecodeType.TypeB);
    reader.SetSourceImage(fstr);
    foreach (ReadResult result in reader.ReadItems())
    {
        Console.WriteLine("Item Type: " + result.TypeName);
        Console.WriteLine("Item Text: " + result.Text);
    }
}
```

### <a id="SampleReader_SetReadType_SingleDecodeType___"></a> SetReadType\(params SingleDecodeType\[\]\)

Sets SingleDecodeType type array for recognition.
Must be called before ReadItems() method.

```csharp
public void SetReadType(params SingleDecodeType[] itemTypes)
```

#### Parameters

`itemTypes` [SingleDecodeType](/{{PRODUCT_FAMILY}}/recognition.singledecodetype)\[\]

The SingleDecodeType type array to read.

#### Examples

This sample shows how to detect TypeA and TypeB items.

```csharp
using (SampleReader reader = new SampleReader())
{
    reader.SetReadType(DecodeType.TypeA, DecodeType.TypeB);
    reader.SetSourceImage(@"c:\test.png");
    foreach (ReadResult result in reader.ReadItems())
    {
        Console.WriteLine("Item Type: " + result.TypeName);
        Console.WriteLine("Item Text: " + result.Text);
    }
}
```

### <a id="SampleReader_SetReadType_BaseDecodeType_"></a> SetReadType\(BaseDecodeType\)

Sets decode type for recognition.
Deprecated. Use ReadType property instead.

```csharp
[Obsolete("SetReadType is deprecated. Use the ReadType property instead.", false)]
public void SetReadType(BaseDecodeType type)
```

#### Parameters

`type` [BaseDecodeType](/{{PRODUCT_FAMILY}}/recognition.basedecodetype)

The type to read.
