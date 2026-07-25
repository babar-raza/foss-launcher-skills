//! Module kept under a dotted, non-identifier directory name and wired in via
//! `#[path = ...]` — the Aspose.Cells-FOSS-for-Rust layout. Types here are
//! re-exported at the crate root, so their canonical import is the bare name.

/// A type living in a #[path]-mapped dotted directory.
pub struct FlatType {
    pub id: u32,
}

impl FlatType {
    /// Rust conversion idiom — must NOT be detected as a "vec" file format.
    pub fn to_vec(&self) -> Vec<u8> {
        vec![]
    }

    /// Explicit I/O verb — the only pass-2 format signal that counts for Rust.
    pub fn save_to_xlsx(&self, path: &str) -> Result<(), String> {
        let _ = path;
        Ok(())
    }
}

/// Output formats supported by the fixture crate.
pub enum SaveFormat {
    Xlsx,
}
