"""core/ — Shared utilities for the pipeline.

Modules in this package:
- constants.py:    Shared constants (KNOWLEDGE_ROOT, CONTENT_ROOT, PLATFORM_MAP, etc.)
- models.py:       Unified Finding frozen dataclass with stable deterministic id
- fs.py:           atomic_write, file_hash — safe file mutations
- manifest.py:     write_step_manifest, check_step_complete — pipeline run state
- markdown.py:     _FRONTMATTER_READER_RE, _FRONTMATTER_WRITER_RE, parse_frontmatter
- knowledge.py:    Re-export shim over knowledge_core (enables `from core.knowledge import X`)
- clone_cache.py:  Internal FOSS repo clone cache — cache_root, clone_path, clone_exists,
                   clone_head_sha, ensure_clone.  No dependency on foss-launcher.
- env_loader.py:  load_env() — loads .env from repo root into os.environ via python-dotenv.
                  Call once at the top of every CLI entry point.  No-op if python-dotenv
                  is absent (graceful degradation to shell-exported vars).

Note: knowledge.py imports from knowledge_core (a sibling), so it does not
satisfy the strict "zero upstream deps" rule. All other modules in this
package remain zero-dep.
"""
