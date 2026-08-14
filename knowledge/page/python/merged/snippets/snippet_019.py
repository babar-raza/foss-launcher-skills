def test_create_server_registers_all_tools(self) -> None:
        fake_module = types.ModuleType("fastmcp")
        fake_module.FastMCP = _FakeFastMCP

        with patch.dict(sys.modules, {"fastmcp": fake_module}):
            server = mcp_server.create_server()

        self.assertEqual(server.name, "Aspose.Page")
        self.assertEqual(
            [tool.__name__ for tool in server.tools],
            ["ps_to_pdf", "ps_to_image", "xps_to_pdf", "xps_to_image", "eps_metadata"],
        )