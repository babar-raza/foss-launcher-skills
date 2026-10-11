function rectToQuads(b: Box): number[] {
  const [llx, lly, urx, ury] = b;
  return [llx, ury, urx, ury, llx, lly, urx, lly];
}