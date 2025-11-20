"""Compatibility shim: imports the real driver from backend.willit.prompt_drivers.

This lets older scripts that `import prompt_drivers` continue to work while the
Willit backend uses the in-package implementation.
"""

from backend.willit.prompt_drivers import *  # noqa: F401,F403
