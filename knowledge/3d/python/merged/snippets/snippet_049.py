def test_io_service_registration(self):
        service = IOService()
        exporter = Exporter()
        importer = Importer()
        detector = FormatDetector()
        
        service.register_exporter(exporter)
        service.register_importer(importer)
        service.register_detector(detector)
        
        self.assertIn(exporter, service._exporters)
        self.assertIn(importer, service._importers)
        self.assertIn(detector, service._detectors)