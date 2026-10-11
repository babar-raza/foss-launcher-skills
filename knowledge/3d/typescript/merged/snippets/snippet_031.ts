it('testIoServiceSingleton', () => {
        const service1 = IOService.instance;
        const service2 = IOService.instance;
        expect(service1).toBe(service2);
    })