---
toolRestrictions:
  - toolName: "create_file"
    applyTo: ["output/**"]
    allowed: true
  - toolName: "replace_string_in_file"
    applyTo: ["output/**"]
    allowed: true
  - toolName: "multi_replace_string_in_file"
    applyTo: ["output/**"]
    allowed: true
  - toolName: "edit_notebook_file"
    applyTo: ["output/**"]
    allowed: true
---

# StarCitizenUtilities — Agent Instructions

## Project Overview

Python utilities that parse raw Star Citizen game files (DataForge XML records + localization INI) to produce human-readable output files used as localization overrides for the in-game custom localization feature.

## Key Paths

| Name                   | Path                                                                   |
| ---------------------- | ---------------------------------------------------------------------- |
| Game install           | `G:\RSI\StarCitizen\PTU\`                                              |
| Game pak               | `G:\RSI\StarCitizen\PTU\Data.p4k`                                      |
| Extraction workspace   | `G:\StarCitizenUtilities\extract\`                                     |
| DataForge records root | `G:\StarCitizenUtilities\extract\Data\libs\foundry\records\`           |
| Localization source    | `G:\StarCitizenUtilities\extract\Data\Localization\english\global.ini` |
| Project outputs        | `G:\StarCitizenUtilities\output\`                                      |
| Shared config          | `G:\StarCitizenUtilities\sc_config.py`                                 |

All cross-module path constants live in `sc_config.py` — check there before hardcoding any path.

## Pipeline

```
Data.p4k → unp4k.exe → raw files
Game2.dcb → unforge.cli.exe → extract/Data/libs/foundry/records/**/*.xml
                            → extract/Data/Localization/english/global.ini
```

Then Python submodules parse those XMLs and write to `output/`.

Run everything with `patch_day.py`. Key flags:

- `python patch_day.py` — localization merge only (fast)
- `python patch_day.py --full` — full DataForge extraction + all submodules
- `python patch_day.py --deploy` — copy outputs to game folder

## Submodules & Their Record Directories

| Module                  | Input record path (under `records/`)              | Output                                                               |
| ----------------------- | ------------------------------------------------- | -------------------------------------------------------------------- |
| `sc_ship_components.py` | `entities/scitem/ships/**`, `scitemmanufacturer/` | `ship_components.csv`, `ship_components.ini`                         |
| `sc_ship_armor.py`      | `entities/scitem/ships/**`                        | `ship_armor.csv`                                                     |
| `sc_fps_weapons.py`     | `entities/scitem/fps/**`                          | `fps_weapons.csv`                                                    |
| `sc_missiles.py`        | `entities/scitem/ships/missile/**`                | `missiles.ini`                                                       |
| `sc_missions.py`        | `missiondata/`, `contracts/`                      | `mission_blueprints.ini`                                             |
| `sc_blueprints.py`      | `crafting/`, `cargomanifest/`                     | `blueprints_received.csv`, `blueprint_rewards.csv`                   |
| `sc_localization.py`    | `extract/Data/Localization/english/global.ini`    | `merged.ini`                                                         |
| `sc_ore_locations.py`   | `mining/`, `harvestable/`                         | `ore_elements.csv`, `rock_compositions.csv`, `location_ore_dist.csv` |

## DataForge XML Format

All records share this structure:

```xml
<TypeName.RecordName attr1="val" attr2="val"
  __type="TypeName"
  __ref="guid-uuid-here"
  __path="libs/foundry/records/relative/path.xml">
  <childElement>...</childElement>
</TypeName.RecordName>
```

- **`__ref`** — unique GUID for the record; used cross-file as a foreign key
- **`__type`** — the data type (matches the tag prefix before `.`)
- References between records use `<Reference value="guid" />` or attribute `someField="guid"`

## Key Game Data Directories (under `records/`)

### Items / Ships

- `entities/scitem/ships/` — all ship-equippable components; subdirs by type (weapons, shields, coolers, etc.)
- `entities/scitem/fps/` — FPS gear (weapons, armor, gadgets)
- `scitemmanufacturer/` — manufacturer display names keyed by GUID

### Mining

- `mining/mineableelements/` — one XML per ore/mineral; contains instability, resistance, optimal window properties
- `mining/rockcompositionpresets/` — rock composition templates; subdirs:
  - `asteroidshipmining/` — ship-mined asteroid compositions by rarity tier
  - `surfaceshipmining/` — surface deposit compositions by rock type (gneiss, shale, granite, etc.)
- `mining/miningglobalparams.xml` — global mining constants (mass, power, explosion params)
- `mining/miningcontrollerparamsship.xml` — ship scanner/HUD settings
- `mining/mineableelements/minableelement_fps_*.xml` — FPS hand-mining gems

### Harvestables / Spawning

- `harvestable/providerpresets/system/stanton/` — per-location spawn tables (planets + asteroid fields)
- `harvestable/providerpresets/system/pyro/` — Pyro system locations
- `harvestable/providerpresets/system/nyx/` — Nyx system asteroid belts
- `harvestable/harvestablepresets/` — harvestable preset library (mining*\*, fpsmining*\_, groundvehiclemining\_\_)
- `harvestable/clusteringpresets/` — asteroid cluster density configs

### Economy / Cargo

- `commodityconfiguration/` — buy/sell price configs
- `commoditytypedatabase/` — commodity type metadata
- `cargomanifest/` — cargo container definitions
- `refiningprocess/` — refinery processing type parameters
- `resourcetypedatabase/resourcetypedatabase.xml` — resource type registry

### Missions / Contracts

- `missiondata/` — mission template definitions
- `contracts/` — contract/job definitions
- `missiongiver/` — NPC mission giver configs
- `missiontype/` — mission category types

### Crafting / Blueprints

- `crafting/` — blueprint/schematic definitions
- `lootgeneration/` — loot table definitions including blueprint rewards

### World / Solar System

- `ssolarsystem/stanton.xml`, `pyro.xml`, `nyx.xml` — top-level solar system records
- `harvestable/providerpresets/system/stanton/asteroidfield/` — named asteroid fields (Aaron Halo, Lagrange points, Yela Belt)

### Characters / NPCs

- `actor/` — actor entity definitions
- `factions/` — faction data
- `reputation/` — reputation value settings

## Location Name Mapping

Stanton planet/moon HPP files map as:

- `hpp_stanton1` → Hurston | `hpp_stanton1a/b/c/d` → Arial, Aberdeen, Magda, Ita
- `hpp_stanton2a/b/c` → Cellin, Daymar, Yela
- `hpp_stanton3a/b` → Lyria, Wala
- `hpp_stanton4` → MicroTech | `hpp_stanton4a/b/c` → Calliope, Clio, Euterpe

Pyro: `hpp_pyro1`=Ignis, `hpp_pyro2`=Monox, `hpp_pyro3`=Pyro III, `hpp_pyro4`=Bloom, `hpp_pyro5a-f`=Pyro V moons, `hpp_pyro6`=Terminus

Nyx asteroid fields: `hpp_nyx_glaciemring`, `hpp_nyx_keegerbelt`

## Ore Rarity Tiers

| Tier           | Ship Mining Examples                                     | FPS Mining Examples                    |
| -------------- | -------------------------------------------------------- | -------------------------------------- |
| Common         | Aluminum, Copper, Iron, Quartz, Silicon, Tin, Corundum   | Aphorite, Dolivine, Hadanite, Janalite |
| Uncommon       | Agricium, Aslarite, Laranite, Titanium, Torite, Tungsten | Carinite, Saldynium                    |
| Rare           | Beryl, Bexalite, Borase, Gold, Taranite                  | Jaclium, Sadaryx                       |
| Epic           | Lindinium, Ouratite, Riccite                             | —                                      |
| Legendary      | Quantainium, Savrilium, Stileron                         | —                                      |
| Ground Vehicle | Beradom, Carinite, Feynmaline, Glacosite                 | —                                      |

## Rock Composition Structure

All `MineableComposition` records follow this pattern for ship-mined asteroids:

```xml
<MineableCompositionPart
  mineableElement="[ore-guid]"
  minPercentage="N"
  maxPercentage="N"
  probability="0-1"
  curveExponent="1"        <!-- 1=uniform random; >1=bell; <1=U-shaped -->
  qualityScale="0-1" />    <!-- yield multiplier; 1.0=full, 0.49=low grade -->
```

All named asteroid compositions use a two-part split:

- Small high-quality component: `2.82–6.82%` at `qualityScale=1.0`
- Large bulk component: `39–93%` at `qualityScale=0.49`
- Optional impurity: `5–10%` at `qualityScale=0.789` (absent in some Common ores)

Quality is template-based, not dynamically calculated per rock.

## Localization Keys

`global.ini` uses `key=value` format. Common key patterns:

- `item_Name_<EntityClass>` — item display name
- `items_commodities_<ore>` — commodity name (e.g. `items_commodities_stileron`)
- `hud_mining_asteroid_name_<N>` — asteroid type display name
- `@hud_mining_asteroid_name_2` — `@` prefix means "look up this key in global.ini"

## Output Files

| File                             | Description                                   |
| -------------------------------- | --------------------------------------------- |
| `output/merged.ini`              | Master localization override deployed to game |
| `output/ship_components.csv`     | All ship components with metadata             |
| `output/ship_components.ini`     | Localization overrides for ship components    |
| `output/fps_weapons.csv`         | FPS weapon metadata                           |
| `output/missiles.ini`            | Missile localization overrides                |
| `output/ship_armor.csv`          | Ship armor metadata                           |
| `output/blueprints_received.csv` | Craftable blueprints                          |
| `output/blueprint_rewards.csv`   | Blueprint mission rewards                     |
| `output/ore_elements.csv`        | All mineable elements with mining properties  |
| `output/rock_compositions.csv`   | Rock composition presets by element           |
| `output/location_ore_dist.csv`   | Per-location ore spawn distribution           |
