/// The value stored in a single cell.
pub enum CellValue {
    /// Numeric value.
    Number(f64),
    Text(String),
    Empty,
}

/// Anything that can be persisted to disk.
pub trait Saveable {
    /// Persists the object to the given path.
    fn save_as(&self, path: &str) -> Result<(), String>;

    /// Returns a stable format tag.
    fn format_tag(&self) -> u32 {
        0
    }
}

#[doc = "Cell coordinate pair."]
pub struct Coord {
    pub row: u32,
    pub col: u32,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn coord_roundtrip() {
        let c = Coord { row: 1, col: 2 };
        assert_eq!(c.row, 1);
    }
}
