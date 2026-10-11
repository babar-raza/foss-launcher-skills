//! Fixture crate exercising every Rust extraction shape the scout must handle.

pub mod cell;
pub mod workbook;
mod internal_util;
mod save;

#[path = "Aspose.Fixture_FOSS/flat.rs"]
mod flat;

pub use flat::{FlatType, SaveFormat};
pub use workbook::Workbook;

/// Opens a workbook from disk.
pub fn open(path: &str) -> Workbook {
    let _ = path;
    Workbook::new()
}

fn private_helper() {}
