[Test]
    public void Rectangle_MutableShape_Updates()
    {
        var rectangle = new Rectangle(new Point(10, 20), new Size(30, 40));

        rectangle.Location = new Point(15, 25);
        rectangle.Size = new Size(35, 45);
        rectangle.Right = 60;
        rectangle.Bottom = 80;

        Assert.That(rectangle.X, Is.EqualTo(15));
        Assert.That(rectangle.Y, Is.EqualTo(25));
        Assert.That(rectangle.Width, Is.EqualTo(45));
        Assert.That(rectangle.Height, Is.EqualTo(55));
        Assert.That(rectangle.Contains(new Point(30, 40)), Is.True);
        Assert.That(rectangle.IntersectsWith(Rectangle.FromLeftTopRightBottom(50, 70, 70, 90)), Is.True);

        rectangle.Offset(new Point(5, -5));
        rectangle.Inflate(new Size(1, 2));

        Assert.That(rectangle, Is.EqualTo(Rectangle.FromLeftTopRightBottom(19, 18, 66, 77)));
    }