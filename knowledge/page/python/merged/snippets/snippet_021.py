def test_run_invokes_server_with_host_port(self) -> None:
        fake = _FakeFastMCP("Aspose.Page")
        with patch("aspose.page.mcp.server.create_server", return_value=fake):
            mcp_server.run(host="0.0.0.0", port=8123)
        self.assertEqual(fake.run_calls, [("0.0.0.0", 8123)])