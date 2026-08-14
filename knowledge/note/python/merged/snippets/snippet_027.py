def test_license_and_metered_are_callable(self) -> None:
        from aspose.note import License, Metered

        lic = License()
        lic.SetLicense("dummy.lic")

        m = Metered()
        m.SetMeteredKey("pub", "priv")