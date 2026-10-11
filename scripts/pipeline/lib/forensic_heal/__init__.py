"""forensic_heal — shared library package for S-122 (blind-spot-audit) and S-123
(forensic-heal-sprint), Mission MT025-2026-08-08-FORENSIC-BLIND-SPOT-HEAL-SKILLS.

Modules land incrementally per the mission's wave plan
(plans/missions/MT025-2026-08-08-FORENSIC-BLIND-SPOT-HEAL-SKILLS.md):
  manual_first_audit  — Wave 2: L2 skill-invocation ledger audit, L3 artifact-mtime
                         forensics (the unaided-first hard gate backing S-122's seal()).
  blind_spot_matrix    — Wave 3: manual-vs-system finding classification.
  root_cause_model     — Wave 3: layer attribution for root causes.
  taskcard_bridge       — Wave 3/4: findings/root-causes -> schema-5f taskcard rows.
  adversarial_probes   — Wave 5: S-123's 12 named probes.
  verdict               — Wave 5: computed (not asserted) dual verdicts.
"""
