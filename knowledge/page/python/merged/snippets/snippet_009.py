def test_render_size_respects_dpi(self) -> None:
        doc = RenderDocument()
        page = RenderPage(width=72, height=72)
        page.commands.append(
            PathCommand(
                path=rect_path(Rect(0, 0, 72, 72)),
                stroke=None,
                fill=Paint("DeviceRGB", (1.0, 0.0, 0.0)),
            )
        )
        doc.pages.append(page)
        surface_72 = RasterRenderer(dpi=72).render(doc)
        surface_144 = RasterRenderer(dpi=144).render(doc)
        self.assertEqual(surface_72.width, 72)
        self.assertEqual(surface_72.height, 72)
        self.assertEqual(surface_144.width, 144)
        self.assertEqual(surface_144.height, 144)