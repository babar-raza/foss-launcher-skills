/**
 * Represents a loaded document.
 */
export class Document {
  static open(path: string): Document {
    return new Document();
  }

  save(path: string): void {
    // write to disk
  }
}
