using System.IO;
using Aspose.Email.Foss.Msg;
using var stream = File.OpenRead("sample.msg");

var message = MapiMessage.FromStream(stream);
Console.WriteLine(message.Subject);
