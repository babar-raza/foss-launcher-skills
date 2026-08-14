def test_auto_filter_xml_structure(self):
        """Test that auto filter XML structure is correct."""
        wb = Workbook()
        ws = wb.worksheets[0]
        
        # Add some data
        ws.cells['A1'].value = "Name"
        ws.cells['B1'].value = "Age"
        ws.cells['A2'].value = "Alice"
        ws.cells['B2'].value = 30
        
        # Set auto filter range and apply filter
        ws.auto_filter.range = "A1:B2"
        ws.auto_filter.filter(0, ["Alice"])
        
        # Save file
        test_file = os.path.join(self.output_dir, 'test_auto_filter_xml_structure.xlsx')
        wb.save(test_file)
        
        # Read and verify XML structure
        with zipfile.ZipFile(test_file, 'r') as zf:
            sheet_xml = zf.read('xl/worksheets/sheet1.xml')
            root = ET.fromstring(sheet_xml)
            ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            
            # Verify autoFilter element exists
            auto_filter = root.find('.//ns:autoFilter', ns)
            self.assertIsNotNone(auto_filter)
            self.assertEqual(auto_filter.attrib.get('ref'), 'A1:B2')
            
            # Verify filterColumn element exists
            filter_col = auto_filter.find('ns:filterColumn', ns)
            self.assertIsNotNone(filter_col)
            self.assertEqual(int(filter_col.attrib.get('colId')), 0)
            
            # Verify filters element exists
            filters = filter_col.find('ns:filters', ns)
            self.assertIsNotNone(filters)
            
            # Verify filter element exists
            filter_elem = filters.find('ns:filter', ns)
            self.assertIsNotNone(filter_elem)
            self.assertEqual(filter_elem.attrib.get('val'), 'Alice')