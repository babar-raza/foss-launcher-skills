private static void generateChartDirs(Path cp, Path src) throws IOException {
        Map<String, ChartType> cd = new LinkedHashMap<>();
        cd.put("ColumnChart",ChartType.COLUMN); cd.put("AreaChart",ChartType.AREA);
        cd.put("BarChart",ChartType.BAR); cd.put("linechart",ChartType.LINE);
        cd.put("PieChart",ChartType.PIE); cd.put("XYChart",ChartType.SCATTER);
        cd.put("RadarChart",ChartType.RADAR); cd.put("SurfaceChart",ChartType.SURFACE_3D);
        cd.put("StockChart",ChartType.STOCK);
        for (Map.Entry<String, ChartType> e : cd.entrySet()) {
            Workbook wb = ChartScenarioFactory.createChartWorkbook(e.getValue(), "Sheet1");
            saveWorkbook(wb, cp.resolve(e.getKey()).resolve("chart.xlsx"));
            saveWorkbook(wb, src.resolve(e.getKey()).resolve("chart.xlsx"));
        }
        String[] simple = {"FunnelChart","HistogramChart","BoxChart","SunburstChart",
            "TreemapChart","MapChart","combochart","waterfallchart","allcharts","Sparkline"};
        for (String d : simple) {
            Workbook wb = new Workbook();
            saveWorkbook(wb, cp.resolve(d).resolve("chart.xlsx"));
            saveWorkbook(wb, src.resolve(d).resolve("chart.xlsx"));
        }
    }