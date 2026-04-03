---
linkTitle: Scene
title: Scene
description: Represents a 3D scene containing nodes, meshes, and scene-level metadata.
summary: Root container for a 3D scene graph.
categories:
- Class
layout: single
evidence:
  model_sha: 37114723be16c9c9441c8fb93116b044ad1aa6b5
  model_version: 26.1.0
  claims:
  - CLM-3d-46f64e
  apis:
  - Scene.from_file
grade: B
graded_at: "2026-01-15T00:00:00Z"
graded_model_sha: 37114723be16c9c9441c8fb93116b044ad1aa6b5
graded_evaluators: full
graded_logic_version: 2
provenance:
  content_origin: unknown
  last_mechanism: grade-writer
  auto_updatable: true
  reviewed: false
---

## Overview

`Scene` is the root container for a 3D scene graph.

## Methods

| Method | Description |
|--------|-------------|
| `Scene.from_file(path)` | Load a scene from a file |
