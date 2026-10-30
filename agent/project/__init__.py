"""Coal Project Awareness: multi-file project memory, journaling,
audit, and context so coding never hallucinates about the codebase.

  from project import Project, Journal, Auditor, project_context
"""
from .project import Project, desktop_root, slugify, safe_name
from .journal import Journal
from .audit import Auditor
from .context import project_context, file_context

__all__ = ["Project", "Journal", "Auditor", "project_context",
           "file_context", "desktop_root", "slugify", "safe_name"]