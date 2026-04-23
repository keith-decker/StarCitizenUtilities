# Patch Day Checklist

Steps to complete before running `patch_day.py` on a new game version.

---

## One-Time Setup

These only need to be done once (or after reinstalling tools/game).

1. **Python 3.6+** installed and on your PATH
   Verify: `python --version`

2. **unp4k tools** present at `G:\un4pk\`
   - `unp4k.exe` — extracts files from `Data.p4k`
   - `unforge.exe` — extracts DataForge records from `Game2.dcb`

3. **Star Citizen** installed at `G:\RSI\StarCitizen\LIVE\`

4. **Language set to English** in your game `user.cfg`:
   ```
   g_language = english
   ```
   The `user.cfg` file lives in `G:\RSI\StarCitizen\LIVE\` (create it if it doesn't exist).

5. **target_strings.ini** populated with your manual overrides (`G:\StarCitizenUtilities\target_strings.ini`).
   Contains: vehicle names, commodity short names, and any one-off manual fixes.
   Does **not** contain mission text or component names — those are auto-generated.

---

## Before Each Patch Day Run

1. **Let the game fully patch** — wait for the launcher to finish updating before running the script. The script reads `Data.p4k` and `Game2.dcb` directly from the game folder.

2. **Close Star Citizen** if it is running.

---

## Running the Script

### Localization merge only (fast — no DataForge extraction)

```powershell
python patch_day.py                   # merge only, no deploy
python patch_day.py --deploy          # merge + copy to game folder
```

### Full pipeline (recommended on patch day)

```powershell
python patch_day.py --full            # extract + merge, no deploy
python patch_day.py --full --deploy   # extract + merge + deploy to game
```

`--full` additionally:
- Runs `unforge.exe` to extract all DataForge records from `Game2.dcb`
- Rebuilds `blueprint_rewards.csv` from contract/crafting XML records
- Rebuilds `ship_components.csv` and `ship_components.ini` from item XML records
- Rebuilds `mission_blueprints.ini` — mission description overrides with blueprint reward
  lists appended, plus `[BP]` tags on matching mission titles

### Re-run generation without re-extracting DCB (saves time when iterating)

```powershell
python patch_day.py --full --skip-dcb          # skip unforge, reuse existing records
python patch_day.py --full --skip-dcb --deploy # same + deploy
```

---

## Output Files

| File | Description | In git? |
|---|---|---|
| `src\global.ini` | Raw localization extracted from `Data.p4k` | No |
| `output\merged.ini` | Final merged localization (deploy this) | No |
| `output\blueprint_rewards.csv` | Mission → blueprint reward rows (`--full`) | Yes |
| `output\ship_components.csv` | Ship component name rows (`--full`) | Yes |
| `ship_components.ini` | Auto-generated component name overrides (`--full`) | No |
| `mission_blueprints.ini` | Auto-generated mission description + title overrides (`--full`) | No |
| `unresolved_blueprint_items.md` | Items whose names couldn't be resolved from `global.ini` | No |
| `G:\RSI\StarCitizen\LIVE\Data\Localization\english\global.ini` | Live game file (`--deploy` only) | — |

---

## Override Merge Order

Overrides are applied lowest → highest priority:

1. `ship_components.ini` — auto-generated component names (Grade/Class formatted)
2. `mission_blueprints.ini` — auto-generated mission descriptions + `[BP]` title tags
3. `target_strings.ini` — your manual overrides (always wins)

---

## After a Patch: Things to Check

- **Substitution count drops** — a game patch may have renamed or removed a key in `target_strings.ini`. Compare `src\global.ini` against your overrides for stale keys.
- **New blueprint items unresolved** — check `unresolved_blueprint_items.md`. Items listed there appear as raw IDs in mission text because their display name wasn't found in `global.ini`.
- **New component types** — if new equipment categories appear (e.g. a new component type), they may need adding to `COMPONENT_TYPES` in `sc_config.py`.
