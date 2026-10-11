def test_io_service_singleton(self):
        service1 = IOService()
        service2 = IOService()
        self.assertIs(service1, service2)