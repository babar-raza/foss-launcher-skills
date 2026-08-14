TEST_F(SlidesIntegrationTest, IterateSlides) {
    Presentation pres;
    auto* layout = &pres.layout_slides()[0];
    pres.slides().add_empty_slide(layout);
    std::vector<Slide*> slides;
    for (auto& s : pres.slides()) {
        slides.push_back(s.get());
    }
    EXPECT_EQ(slides.size(), 2);
}