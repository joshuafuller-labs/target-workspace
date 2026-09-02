"""FastAPI application for Target Workspace.

Per ADR 0013 (API client-agnostic) the API surface is public — designed for
the web SPA, future native mobile, ATAK plugins, third-party integrators,
and curl one-liners equally.
"""

from target_workspace.api.app import create_app

__all__ = ["create_app"]
