use crate::cell::Saveable;
use crate::workbook::Workbook;

impl Saveable for Workbook {
    fn save_as(&self, path: &str) -> Result<(), String> {
        self.save(path)
    }
}
