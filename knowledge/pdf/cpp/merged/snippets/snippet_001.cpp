TEST(ActionsSmoke, NamedActionFromPredefined) {
    EXPECT_EQ(static_cast<int>(PredefinedAction::FirstPage), 0);
    EXPECT_EQ(static_cast<int>(PredefinedAction::Window_FullScreenMode), 70);

    NamedAction a{PredefinedAction::NextPage};
    EXPECT_EQ(a.Name(), "NextPage");
    EXPECT_EQ(a.ToString(), "NextPage");
    a.Name("FirstPage");
    EXPECT_EQ(a.Name(), "FirstPage");
}