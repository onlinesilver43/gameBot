# Configuration Guide

This document provides comprehensive documentation for all Brighter Shores Bot configuration files and options.

## Overview

The bot uses a hierarchical configuration system with the following priority (highest to lowest):
1. Environment variables
2. API parameters (runtime overrides)
3. Configuration files
4. Built-in defaults

## Directory Structure

```
config/
├── profile.yml          # Main profile configuration
├── keys.yml            # Key bindings
├── monsters/           # Monster detection profiles
│   ├── twisted_wendigo.yml
│   ├── common_viper.yml
│   └── ...
└── interfaces/         # UI interface definitions
    └── combat.yml
```

---

## Main Profile Configuration

File: `config/profile.yml`

This file contains global settings that apply to all detection sessions.

### Example Configuration

```yaml
# Brighter Shores Bot Profile Configuration
# Window and runtime settings

# Game Window
window_title: "Brighter Shores"
monitor_index: 1  # 0=primary, 1=secondary, etc.

# Window Position/Size
x: 0
y: 0
width: 1280
height: 720

# UI Scaling (if game supports it)
ui_scale: 1.0

# Runtime Settings
input_delay_ms: 200
scan_interval_ms: 500
action_timeout_ms: 5000

# Safety Settings
panic_key: "ctrl+alt+p"
health_threshold: 0.3
mana_threshold: 0.2

# Detection Settings
detection_method: "template"  # template, ocr, or auto
confidence_threshold: 0.65
roi_x: 0.2
roi_y: 0.25
roi_width: 0.6
roi_height: 0.5

# Profile Defaults
default_monster: "twisted_wendigo"
default_interface: "combat"
default_template_path: "assets/templates/wendigo.png"
tesseract_path: "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"

# Debug Settings
debug_enabled: false
log_level: "INFO"
save_screenshots: false
```

### Configuration Fields

#### Game Window Settings
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `window_title` | string | "Brighter Shores" | Exact window title to target |
| `monitor_index` | integer | 1 | Monitor index (0=primary, 1=secondary) |
| `x` | integer | 0 | Window X position |
| `y` | integer | 0 | Window Y position |
| `width` | integer | 1280 | Window width |
| `height` | integer | 720 | Window height |
| `ui_scale` | float | 1.0 | UI scaling factor |

#### Runtime Settings
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `input_delay_ms` | integer | 200 | Delay between inputs (ms) |
| `scan_interval_ms` | integer | 500 | Time between scans (ms) |
| `action_timeout_ms` | integer | 5000 | Timeout for actions (ms) |

#### Safety Settings
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `panic_key` | string | "ctrl+alt+p" | Global pause/resume hotkey |
| `health_threshold` | float | 0.3 | Health percentage to trigger safety |
| `mana_threshold` | float | 0.2 | Mana percentage to trigger safety |

#### Detection Settings
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `detection_method` | string | "template" | Primary detection method |
| `confidence_threshold` | float | 0.65 | Minimum confidence for detection |
| `roi_x` | float | 0.2 | Region of interest X (0.0-1.0) |
| `roi_y` | float | 0.25 | Region of interest Y (0.0-1.0) |
| `roi_width` | float | 0.6 | Region of interest width (0.0-1.0) |
| `roi_height` | float | 0.5 | Region of interest height (0.0-1.0) |

#### Profile Defaults
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `default_monster` | string | "twisted_wendigo" | Default monster profile |
| `default_interface` | string | "combat" | Default interface profile |
| `default_template_path` | string | null | Default template image path |
| `tesseract_path` | string | null | Path to Tesseract executable |

#### Debug Settings
| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `debug_enabled` | boolean | false | Enable debug features |
| `log_level` | string | "INFO" | Logging level |
| `save_screenshots` | boolean | false | Save debug screenshots |

---

## Key Bindings Configuration

File: `config/keys.yml`

Defines key bindings for in-game actions.

### Example Configuration

```yaml
# Brighter Shores Key Bindings
# Customize these to match your game's key setup

# Combat Actions
attack: "left_click"
special_attack: "right_click"
target_nearest: "tab"
target_next: "q"

# Movement
move_forward: "w"
move_backward: "s"
move_left: "a"
move_right: "d"
sprint: "shift"

# Abilities & Items
heal: "1"
mana_restore: "2"
buff: "3"

# UI & Interaction
inventory: "i"
character: "c"
map: "m"
interact: "e"
loot: "f"

# System
menu: "esc"
quest_log: "j"
```

### Key Binding Categories

#### Combat Actions
| Key | Default | Description |
|-----|---------|-------------|
| `attack` | "left_click" | Primary attack |
| `special_attack` | "right_click" | Special attack |
| `target_nearest` | "tab" | Target nearest enemy |
| `target_next` | "q" | Cycle to next target |

#### Movement Keys
| Key | Default | Description |
|-----|---------|-------------|
| `move_forward` | "w" | Move forward |
| `move_backward` | "s" | Move backward |
| `move_left` | "a" | Strafe left |
| `move_right` | "d" | Strafe right |
| `sprint` | "shift" | Sprint modifier |

#### Abilities & Items
| Key | Default | Description |
|-----|---------|-------------|
| `heal` | "1" | Use healing item/ability |
| `mana_restore` | "2" | Restore mana |
| `buff` | "3" | Apply buff |

#### UI & Interaction
| Key | Default | Description |
|-----|---------|-------------|
| `inventory` | "i" | Open inventory |
| `character` | "c" | Open character sheet |
| `map` | "m" | Open map |
| `interact` | "e" | Interact with object |
| `loot` | "f" | Loot container/corpse |

#### System Keys
| Key | Default | Description |
|-----|---------|-------------|
| `menu` | "esc" | Open system menu |
| `quest_log` | "j" | Open quest log |

---

## Monster Profiles

Directory: `config/monsters/`

Each monster profile defines detection parameters for a specific enemy type.

### Profile Structure

```yaml
id: twisted_wendigo
name: "Twisted Wendigo"
word: "Wendigo"
prefix: "Twisted"
attack_word: "Attack"
template: "assets/templates/wendigo.png"
```

### Monster Profile Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Unique profile identifier |
| `name` | string | No | Human-readable name |
| `word` | string | Yes | Primary OCR target word |
| `prefix` | string | No | Secondary OCR target word (for variants) |
| `attack_word` | string | No | Attack button text |
| `template` | string | No | Template image path |

### Available Monster Profiles

| Profile ID | Name | Primary Word | Prefix | Template |
|------------|------|--------------|--------|----------|
| `twisted_wendigo` | Twisted Wendigo | "Wendigo" | "Twisted" | wendigo.png |
| `common_viper` | Common Viper | "Viper" | null | viper.png |
| `lean_spriggan` | Lean Spriggan | "Spriggan" | "Lean" | spriggan.png |
| `murmuring_shade` | Murmuring Shade | "Shade" | "Murmuring" | shade.png |
| `rotting_bramblelith` | Rotting Bramblelith | "Bramblelith" | "Rotting" | bramblelith.png |
| `haggard_minecrawler` | Haggard Minecrawler | "Minecrawler" | "Haggard" | minecrawler.png |

---

## Interface Profiles

Directory: `config/interfaces/`

Interface profiles define UI element recognition patterns for different game interfaces.

### Combat Interface Example

File: `config/interfaces/combat.yml`

```yaml
id: combat
name: "Combat HUD"
attack_word: "Attack"
prepare_targets:
  - "prepare"
  - "choose"
weapon_digits:
  - "1"
  - "2"
  - "3"
special_tokens:
  - "special"
  - "attacks"
```

### Interface Profile Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique interface identifier |
| `name` | string | Human-readable name |
| `attack_word` | string | Attack button OCR text |
| `prepare_targets` | array | OCR words for prepare/battle screen |
| `weapon_digits` | array | Weapon slot digit recognition |
| `special_tokens` | array | Special attacks OCR tokens |

---

## Environment Variables

Environment variables can override configuration file values.

### Runtime Overrides
| Variable | Maps to | Description |
|----------|---------|-------------|
| `BSBOT_TITLE` | `window_title` | Override window title |
| `BSBOT_WORD` | `word` | Override target word |
| `BSBOT_METHOD` | `detection_method` | Override detection method |
| `BSBOT_CLICK_MODE` | `click_mode` | Override click mode |
| `TESSERACT_PATH` | `tesseract_path` | Override Tesseract path |
| `LOG_LEVEL` | `log_level` | Override log level |

### Example Usage
```bash
# Override window title
export BSBOT_TITLE="My Game Window"

# Override detection method
export BSBOT_METHOD="ocr"

# Set Tesseract path
export TESSERACT_PATH="C:\Program Files\Tesseract-OCR\tesseract.exe"

# Run with custom settings
python -m bsbot.ui.server
```

---

## Configuration Validation

### Required Files
- Configuration files are optional - the bot runs with defaults if files don't exist
- Missing files are logged but don't prevent startup
- Invalid YAML syntax causes startup errors

### Validation Rules
- Numeric values must be within valid ranges
- File paths must be accessible (validated at runtime)
- Enum values must match allowed options
- ROI coordinates must be between 0.0 and 1.0

### Common Issues

#### File Not Found
```
WARNING: Config file not found: config/profile.yml
Using default values...
```

#### Invalid YAML
```
ERROR: Invalid YAML in config/profile.yml: mapping values are not allowed here
```

#### Invalid Path
```
ERROR: Template file not found: assets/templates/missing.png
```

---

## Best Practices

### 1. Profile Organization
- Use descriptive names for custom profiles
- Group related monsters by type or location
- Document profile-specific requirements

### 2. Template Management
- Store templates in `assets/templates/` with descriptive names
- Use PNG format for best compatibility
- Test templates across different lighting conditions

### 3. Key Binding Customization
- Map keys to match your actual game setup
- Test key bindings before live operation
- Document custom key setups

### 4. Environment Variables
- Use environment variables for deployment-specific overrides
- Document required environment variables for production
- Avoid hardcoding sensitive information

### 5. Version Control
- Commit configuration templates (without sensitive data)
- Use `.gitignore` for local overrides
- Document configuration changes in commit messages

---

## Configuration Examples

### Minimal Configuration
```yaml
# config/profile.yml - Minimal setup
window_title: "Brighter Shores"
detection_method: "ocr"
confidence_threshold: 0.7
```

### Advanced Configuration
```yaml
# config/profile.yml - Full featured
window_title: "Brighter Shores"
detection_method: "auto"
confidence_threshold: 0.8
roi_x: 0.15
roi_y: 0.2
roi_width: 0.7
roi_height: 0.6
default_monster: "twisted_wendigo"
tesseract_path: "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
log_level: "DEBUG"
debug_enabled: true
```

### Custom Monster Profile
```yaml
# config/monsters/custom_boss.yml
id: custom_boss
name: "Custom Boss Monster"
word: "Boss"
prefix: "Ancient"
attack_word: "Attack"
template: "assets/templates/custom_boss.png"
```

---

## Troubleshooting

### Configuration Not Loading
1. Check file permissions on `config/` directory
2. Verify YAML syntax with online validator
3. Check logs for specific error messages
4. Ensure files are UTF-8 encoded

### Template Detection Issues
1. Verify template file exists and is readable
2. Check template dimensions match expected size
3. Adjust confidence threshold if needed
4. Test template with different lighting conditions

### Key Binding Problems
1. Verify key names match platform conventions
2. Test key bindings manually first
3. Check for key conflicts with other applications
4. Ensure game window has focus when testing

### ROI Configuration
1. Use relative coordinates (0.0 to 1.0)
2. Test ROI with preview endpoint
3. Adjust for different screen resolutions
4. Consider UI scaling when setting bounds
