from __future__ import annotations

import pluggy

from the_black_goat.scheduling import Schedule
from the_black_goat.tools import ToolDef

PROJECT_NAME = "the_black_goat"

hookspec = pluggy.HookspecMarker(PROJECT_NAME)
hookimpl = pluggy.HookimplMarker(PROJECT_NAME)


class GoatHooks:
    """Pluggy hookspecs for the-black-goat plugins."""

    @hookspec
    def goat_register_tools(self) -> list[ToolDef]:
        """Return the tools this plugin contributes.

        Returned ToolDefs should be built via `the_black_goat.tool(...)` (atoms)
        or `the_black_goat.durable(atom, ...)` (durable wrappers). The registry
        prefixes each tool's `name` with the plugin's project-name when
        ingesting.
        """

    @hookspec
    def goat_register_schedules(self) -> list[Schedule]:
        """Return cron-driven invocations this plugin contributes.

        Each Schedule references a tool by its qualified name and supplies a
        cron expression + default input. The registry validates that the
        target tool exists at build time and prefixes each Schedule's `name`
        with the registering plugin's project-name.
        """
