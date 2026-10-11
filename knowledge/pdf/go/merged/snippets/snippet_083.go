// Standalone function — encrypts with default all-allow permissions
err := pdf.Encrypt("input.pdf", "output.pdf", "userpass", "ownerpass")

// Simple case on a Document (applied on Save/WriteTo)
doc, _ := pdf.Open("input.pdf")
doc.SetPassword("userpass", "ownerpass")
err = doc.Save("output.pdf")

// Granular permissions (RC4-128, Standard Security Handler R=3).
// Fields omitted from Permissions{} are denied; if SetPermissions is not
// called at all, every operation is allowed (backward compatible default).
doc.SetPermissions(pdf.Permissions{
    AllowPrint:         true,
    AllowCopy:          true,
    AllowAccessibility: true,
})
doc.Save("restricted.pdf")

// One-call unified API via options — equivalent to SetPassword + SetPermissions
// in a single struct; replaces any prior encryption config on the document.
// Algorithm defaults to AES-128 (ISO 32000-1 V=4 R=4 /CFM /AESV2). Pass
// pdf.EncryptionAlgRC4_128 for legacy RC4-128 V=2 R=3 output, or
// pdf.EncryptionAlgAES256 for AES-256 V=5 R=6 (ISO 32000-2; output uses
// %PDF-2.0 header and requires Acrobat DC or another PDF 2.0 viewer).
doc.SetEncryption(pdf.EncryptionOptions{
    UserPassword:  "userpass",
    OwnerPassword: "ownerpass",
    Permissions:   &pdf.Permissions{AllowPrint: true, AllowCopy: true},
    // Algorithm:  pdf.EncryptionAlgAES128, // default
    // Algorithm:  pdf.EncryptionAlgAES256, // ISO 32000-2; produces %PDF-2.0
    // Algorithm:  pdf.EncryptionAlgRC4_128, // legacy
})
doc.Save("restricted.pdf")

// Reading permissions from an encrypted file (works after OpenWithPassword)
doc, _ = pdf.OpenWithPassword("restricted.pdf", "userpass")
perms, ok := doc.Permissions()
if ok {
    fmt.Printf("can print: %v, can copy: %v\n", perms.AllowPrint, perms.AllowCopy)
}

// Edit-in-place: OpenWithPassword preserves the password, so a plain Save
// re-encrypts with the same password. To produce a plaintext copy, call
// RemoveEncryption explicitly before Save.
doc, _ = pdf.OpenWithPassword("restricted.pdf", "userpass")
doc.AddTextWatermark("APPROVED", pdf.TextStyle{Size: 48})
doc.Save("restricted_signed.pdf")          // still encrypted
doc.RemoveEncryption()
doc.Save("decrypted_copy.pdf")             // plaintext

// Change the password, keeping the current algorithm and permissions.
doc, _ = pdf.OpenWithPassword("restricted.pdf", "userpass")
doc.ChangePassword("newuserpass", "")      // empty owner → same as user
doc.Save("restricted.pdf")
