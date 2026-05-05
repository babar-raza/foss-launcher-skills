"""
Translation preflight package.

Provides PreflightChecker and PreflightReport for detecting available
translation backends and selecting the best one before any translation starts.

Usage:
    from translator.preflight import PreflightChecker
    report = PreflightChecker().run()
    print(report.format_summary())
"""
from translator.preflight.checker import PreflightChecker, PreflightReport, BackendCapability, ModelInfo

__all__ = ["PreflightChecker", "PreflightReport", "BackendCapability", "ModelInfo"]
