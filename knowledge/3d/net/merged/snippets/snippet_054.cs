private void CountMeshes(Node node, ref int meshCount, ref int vertexCount, ref int faceCount)
        {
            foreach (var entity in node.Entities)
            {
                if (entity is Mesh mesh)
                {
                    meshCount++;
                    vertexCount += mesh.ControlPoints.Count;
                    faceCount += mesh.PolygonCount;
                }
            }

            foreach (var childNode in node.ChildNodes)
            {
                CountMeshes(childNode, ref meshCount, ref vertexCount, ref faceCount);
            }
        }