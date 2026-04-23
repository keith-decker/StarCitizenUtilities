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

5. **target_strings.ini** populated with your custom overrides (`G:\StarCitizenUtilities\target_strings.ini`)

---

## Before Each Patch Day Run

1. **Let the game fully patch** — wait for the launcher to finish updating before running the script. The script reads `Data.p4k` and `Game2.dcb` directly from the game folder.

2. **Close Star Citizen** if it is running.

---

## Running the Script

```powershell
# Extract, merge, and generate blueprint CSV — does NOT write to game folder
python G:\StarCitizenUtilities\patch_day.py

# Same as above, plus copies merged.ini directly to the game's localization folder
python G:\StarCitizenUtilities\patch_day.py --deploy
```

**Outputs:**

| File | Description |
|---|---|
| `G:\StarCitizenUtilities\src\global.ini` | Raw localization extracted from Data.p4k |
| `G:\StarCitizenUtilities\output\merged.ini` | global.ini with your custom strings applied |
| `G:\un4pk\blueprint_rewards.csv` | Mission → blueprint reward mappings |
| `G:\RSI\StarCitizen\LIVE\Data\Localization\english\global.ini` | Live game file (only with `--deploy`) |

---

## After Updating target_strings.ini

If a game patch renames or removes a key you override, the substitution will silently be skipped (the original game string will appear in the output). The script prints a substitution count at the end — if the number drops unexpectedly compared to prior runs, check `target_strings.ini` for stale keys against the new `src\global.ini`.
