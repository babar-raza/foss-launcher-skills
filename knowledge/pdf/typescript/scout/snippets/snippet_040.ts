function xywh(b: Box): [number, number, number, number] {
  return [b[0], b[1], b[2] - b[0], b[3] - b[1]];
}