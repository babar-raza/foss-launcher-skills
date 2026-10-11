def test_all_create_shapes():
    """
    Run all test cases for creating Excel files with workflow shapes.
    """
    print("\n" + "="*70)
    print("Test: Create Excel Files with Workflow Shapes")
    print("="*70)
    
    test_create_workflow_with_shapes()
    test_create_approval_workflow()
    
    print("\n" + "="*70)
    print("All tests completed successfully!")
    print("="*70 + "\n")