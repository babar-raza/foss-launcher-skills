TEST(ActionsSmoke, JavascriptAction) {
    JavascriptAction a{"app.alert('hi');"};
    EXPECT_EQ(a.Script(), "app.alert('hi');");
    EXPECT_EQ(a.GetECMAScriptString(), "app.alert('hi');");
    a.Script("console.println('x');");
    EXPECT_EQ(a.GetECMAScriptString(), "console.println('x');");
}