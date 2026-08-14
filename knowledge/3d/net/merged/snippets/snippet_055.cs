private void CountNodesByName(Node node, string name, ref int count)
        {
            if (node.Name == name)
            {
                count++;
            }

            foreach (var childNode in node.ChildNodes)
            {
                CountNodesByName(childNode, name, ref count);
            }
        }