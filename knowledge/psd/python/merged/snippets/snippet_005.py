def test_rectangle_mutableshape_updates(self):
        rectangle = Rectangle(Point(10, 20), Size(30, 40))

        rectangle.location = Point(15, 25)
        rectangle.size = Size(35, 45)
        rectangle.right = 60
        rectangle.bottom = 80

        assert rectangle.x == 15
        assert rectangle.y == 25
        assert rectangle.width == 45
        assert rectangle.height == 55
        assert rectangle.contains(Point(30, 40)) is True
        assert rectangle.intersects_with(
            Rectangle.from_left_top_right_bottom(50, 70, 70, 90)
        ) is True

        rectangle.offset(Point(5, -5))
        rectangle.inflate(Size(1, 2))

        assert rectangle == Rectangle.from_left_top_right_bottom(19, 18, 66, 77)