function centeredRect(outer: Box, w: number, h: number): Box {
  const cx = (outer[0] + outer[2]) / 2;
  const cy = (outer[1] + outer[3]) / 2;
  return [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2];
}