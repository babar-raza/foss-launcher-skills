// Export: {"name": {"type": "text", "value": "Jane"}, "subscribe": {"type": "checkbox", "value": true}, ...}
data, _ := doc.Form().ExportJSON(pdf.JSONExportOptions{Indent: true})

// Fill a template from a JSON payload; n = number of fields applied
n, _ := template.Form().ImportJSON(data)
