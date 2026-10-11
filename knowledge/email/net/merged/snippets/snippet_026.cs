using System.IO;
using Aspose.Email.Foss.Msg;
using var input = File.OpenRead("message.eml");

var message = MapiMessage.LoadFromEml(input);
using var msgOutput = File.Create("message.msg");
message.Save(msgOutput);
using var emlOutput = File.Create("roundtrip.eml");
message.SaveToEml(emlOutput);
