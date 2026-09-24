# Maintaining AssetKit

The canonical installable skill is `skills/assetkit/`. Keep SKILL.md short and put detailed rules in references/.
Runtime scripts must use Python 3.10+ standard library only. Assets in the skill are templates, not project ledger entries.
Do not initialize a business asset ledger in this repository just to edit the skill's code or documentation.
Keep project state outside installed skills. Never replace a user's existing AGENTS.md or CLAUDE.md wholesale.
Before submitting changes, run `python -m unittest discover -s tests -v` and check all relative SKILL.md links.
Do not claim implicit activation or host compatibility was tested unless the host was actually exercised.
