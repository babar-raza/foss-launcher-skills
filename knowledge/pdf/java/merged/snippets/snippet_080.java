private static boolean isFinderRow(boolean[][] m, int row, int col) {
        for (int dx = 0; dx < 7; dx++) {
            if (!m[row][col + dx]) {
                return false;
            }
        }
        return true;
    }