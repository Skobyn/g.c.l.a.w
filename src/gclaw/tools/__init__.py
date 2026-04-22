"""GClaw tool package.

Importing this package imports every tool module so that the
``@tool_export`` decorator registers every builtin function into the
catalog registry as a side effect. ``main.py`` calls the seeder once
after this import, which reflects the registry into Firestore.

Modules without ``@tool_export``-decorated functions (e.g. ``gh``,
``gws``, ``governance``) are safe to re-export here too — they have
no side effects.
"""

from __future__ import annotations

# Public tool modules (ones that contribute @tool_export entries).
from gclaw.tools import (  # noqa: F401
    comms_tools,
    context_tools,
    dev_tools,
    home_tools,
    image_gen_tools,
    postiz_tools,
    research_tools,
    user_profile_tools,
    workspace_tools,
)
