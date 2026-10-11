/// A spreadsheet workbook.
/// Holds worksheets and document properties.
#[derive(Debug, Clone)]
pub struct Workbook {
    /// File system path of the workbook.
    pub path: String,
    pub sheet_count: usize,
    pub(crate) dirty: bool,
    internal_id: u64,
}

impl Workbook {
    /// Creates a new empty workbook.
    pub fn new() -> Self {
        Workbook {
            path: String::new(),
            sheet_count: 0,
            dirty: false,
            internal_id: 0,
        }
    }

    /// Saves the workbook to the given path.
    pub fn save(&self, path: &str) -> Result<(), String> {
        let _ = path;
        Ok(())
    }

    /// Exports the workbook to PDF.
    pub fn export_pdf(&self, path: &str) -> Result<(), String> {
        let _ = path;
        unimplemented!()
    }

    fn touch(&mut self) {
        self.dirty = true;
    }
}

/// A borrowed reference to a sheet-like value.
pub struct SheetRef<'a, T> {
    pub inner: &'a T,
}

pub(crate) struct HiddenState {
    pub raw: u32,
}
