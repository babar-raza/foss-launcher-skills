def test_comprehensive_alignment_settings(self):
        """Test creating all alignment settings and applying them to different cells."""
        # Test data for comprehensive alignment testing
        alignment_test_cases = [
            {
                'cell': 'A1',
                'value': 'Default Alignment',
                'description': 'Default alignment settings',
                'expected_alignment': {
                    'horizontal': 'general',
                    'vertical': 'bottom',
                    'wrap_text': False,
                    'shrink_to_fit': False,
                    'indent': 0,
                    'text_rotation': 0,
                    'reading_order': 0,
                    'relative_indent': 0
                }
            },
            {
                'cell': 'A2',
                'value': 'Left Top',
                'horizontal': 'left',
                'vertical': 'top',
                'description': 'Left horizontal, Top vertical',
                'expected_alignment': {
                    'horizontal': 'left',
                    'vertical': 'top',
                    'wrap_text': False,
                    'shrink_to_fit': False,
                    'indent': 0,
                    'text_rotation': 0,
                    'reading_order': 0,
                    'relative_indent': 0
                }
            },
            {
                'cell': 'A3',
                'value': 'Center Center',
                'horizontal': 'center',
                'vertical': 'center',
                'description': 'Center horizontal, Center vertical',
                'expected_alignment': {
                    'horizontal': 'center',
                    'vertical': 'center',
                    'wrap_text': False,
                    'shrink_to_fit': False,
                    'indent': 0,
                    'text_rotation': 0,
                    'reading_order': 0,
                    'relative_indent': 0
                }
            },
            {
                'cell': 'A4',
                'value': 'Right Bottom',
                'horizontal': 'right',
                'vertical': 'bottom',
                'description': 'Right horizontal, Bottom vertical',
                'expected_alignment': {
                    'horizontal': 'right',
                    'vertical': 'bottom',
                    'wrap_text': False,
                    'shrink_to_fit': False,
                    'indent': 0,
                    'text_rotation': 0,
                    'reading_order': 0,
                    'relative_indent': 0
                }
            },
            {
                'cell': 'A5',
                'value': 'Fill Justify',
                'horizontal': 'fill',
                'vertical': 'justify',
                'description': 'Fill horizontal, Justify vertical',
                'expected_alignment': {
                    'horizontal': 'fill',
                    'vertical': 'justify',
                    'wrap_text': False,
                    'shrink_to_fit': False,
                    'indent': 0,
                    'text_rotation': 0,
                    'reading_order': 0,
                    'relative_indent': 0
                }
            },
            {
                'cell': 'A6',
                'value': 'CenterContinuous Distributed',
                'horizontal': 'centerContinuous',
                'vertical': 'distributed',
                'description': 'CenterContinuous horizontal, Distributed vertical',
                'expected_alignment': {
                    'horizontal': 'centerContinuous',
                    'vertical': 'distributed',
                    'wrap_text': False,
                    'shrink_to_fit': False,
                    'indent': 0,
                    'text_rotation': 0,
                    'reading_order': 0,
                    'relative_indent': 0
                }
            },
            {
                'cell': 'A7',
                'value': 'Text Wrap',
                'horizontal': 'left',
                'vertical': 'top',
                'wrap_text': True,
                'description': 'Text wrap enabled',
                'expected_alignment': {
                    'horizontal': 'left',
                    'vertical': 'top',
                    'wrap_text': True,
                    'shrink_to_fit': False,
                    'indent': 0,
                    'text_rotation': 0,
                    'reading_order': 0,
                    'relative_indent': 0
                }
            },
            {
                'cell': 'A8',
                'value': 'Shrink to Fit',
                'horizontal': 'center',
                'vertical': 'center',
                'shrink_to_fit': True,
                'description': 'Shrink to fit enabled',
                'expe