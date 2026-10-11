TEST(CompatibilityTests, autofilter_members_follow_supported_patterns)
{
    auto workbook = CreateAutoFilterWorkbook();
    AssertAutoFilter(workbook);
}