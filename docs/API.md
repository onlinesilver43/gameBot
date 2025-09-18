# API Reference

This document provides comprehensive documentation for the Brighter Shores Bot REST API endpoints.

## Overview

The bot exposes a REST API on port 8083 with the following capabilities:
- Runtime control (start/pause/stop)
- Status monitoring
- Live preview images
- Log streaming
- Timeline events
- Diagnostic information

## Base URL
```
http://127.0.0.1:8083
```

## Authentication
No authentication required (localhost only).

---

## Runtime Control Endpoints

### POST /api/start
Starts the detection runtime with specified parameters.

#### Request Body
```json
{
  "title": "Brighter Shores",
  "word": "Wendigo",
  "prefix_word": "Twisted",
  "monster_id": "twisted_wendigo",
  "interface_id": "combat",
  "template": "assets/templates/wendigo.png",
  "method": "auto",
  "tesseract_path": "C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
  "click_mode": "dry_run",
  "skill": "combat",
  "roi": [0.2, 0.25, 0.6, 0.5]
}
```

#### Parameters
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `title` | string | No | "Brighter Shores" | Target window title |
| `word` | string | No | From monster profile | Primary OCR target word |
| `prefix_word` | string | No | From monster profile | Secondary OCR target word |
| `monster_id` | string | No | From profile | Monster profile ID |
| `interface_id` | string | No | From profile | Interface profile ID |
| `template` | string | No | From monster profile | Template image path |
| `method` | string | No | "auto" | Detection method: "auto", "template", "ocr" |
| `tesseract_path` | string | No | From profile/env | Path to Tesseract executable |
| `click_mode` | string | No | "dry_run" | Click mode: "dry_run", "live" |
| `skill` | string | No | "combat" | Active skill controller |
| `roi` | array | No | [0.0, 0.0, 1.0, 1.0] | Region of interest [x, y, w, h] as fractions |

#### Response
```json
{
  "ok": true
}
```

#### Error Responses
- `400 Bad Request` - Invalid parameters
- `500 Internal Server Error` - Runtime start failure

### POST /api/pause
Pauses the active detection runtime.

#### Request Body
None

#### Response
```json
{
  "ok": true
}
```

### POST /api/stop
Stops the detection runtime completely.

#### Request Body
None

#### Response
```json
{
  "ok": true
}
```

---

## Status & Monitoring Endpoints

### GET /api/status
Returns comprehensive runtime status and configuration information.

#### Response
```json
{
  "running": true,
  "paused": false,
  "last_result": {
    "found": true,
    "count": 2,
    "confidence": 0.87,
    "method": "ocr",
    "boxes": [[100, 150, 200, 50], [300, 150, 200, 50]],
    "attack": {
      "found": true,
      "count": 1,
      "confidence": 0.92,
      "boxes": [[250, 300, 150, 40]],
      "word": "Attack"
    },
    "special_attacks": {
      "found": false,
      "confidence": 0.0,
      "special_boxes": [],
      "attacks_boxes": []
    },
    "weapon_1": {
      "found": true,
      "count": 1,
      "confidence": 0.95,
      "boxes": [[400, 500, 30, 30]]
    },
    "prefix": {
      "found": true,
      "count": 1,
      "confidence": 0.89,
      "boxes": [[80, 140, 100, 25]],
      "word": "Twisted"
    },
    "planned_clicks": [
      {
        "x": 250,
        "y": 320,
        "label": "attack_button"
      }
    ],
    "total_detections": 15,
    "roi": [0.2, 0.25, 0.6, 0.5],
    "state": "AttackPanel"
  },
  "title": "Brighter Shores",
  "word": "Wendigo",
  "prefix_word": "Twisted",
  "monster_id": "twisted_wendigo",
  "interface_id": "combat",
  "phase": "Search for Monster",
  "template": "assets/templates/wendigo.png",
  "method": "auto",
  "click_mode": "dry_run",
  "skill": "combat",
  "profile": {
    "window_title": "Brighter Shores",
    "detection_method": "auto",
    "confidence_threshold": 0.65
  },
  "keys": {
    "attack": "left_click",
    "heal": "1"
  },
  "monsters": ["twisted_wendigo", "common_viper"],
  "interfaces": ["combat"]
}
```

#### Response Fields
| Field | Type | Description |
|-------|------|-------------|
| `running` | boolean | Whether runtime is active |
| `paused` | boolean | Whether runtime is paused |
| `last_result` | object | Last detection result (see Detection Result format) |
| `title` | string | Target window title |
| `word` | string | Primary OCR target word |
| `prefix_word` | string | Secondary OCR target word |
| `monster_id` | string | Active monster profile ID |
| `interface_id` | string | Active interface profile ID |
| `phase` | string | Human-readable phase description |
| `template` | string | Template image path |
| `method` | string | Detection method |
| `click_mode` | string | Click mode |
| `skill` | string | Active skill controller |
| `profile` | object | Loaded profile configuration |
| `keys` | object | Loaded key bindings |
| `monsters` | array | Available monster profile IDs |
| `interfaces` | array | Available interface profile IDs |

### GET /api/preview.jpg
Returns the latest captured frame as a JPEG image.

#### Response
- **Content-Type**: `image/jpeg`
- **Status**: `200 OK` with JPEG data, or `204 No Content` if no frame available

#### Query Parameters
None

### GET /api/logs/tail
Returns the last N lines from the application log.

#### Query Parameters
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `n` | integer | 200 | Number of lines to return |

#### Response
- **Content-Type**: `text/plain`
- **Body**: Raw log text with last N lines

#### Example Response
```
2024-01-15 10:30:15 INFO Runtime started | title=Brighter Shores word=Wendigo
2024-01-15 10:30:16 INFO detect | found=True count=1 conf=0.87 method=ocr
2024-01-15 10:30:17 INFO detect_attack | found=True count=1 conf=0.92
```

### GET /api/timeline
Returns the event timeline for debugging and monitoring.

#### Response
```json
[
  {
    "ts": "2024-01-15T10:30:16.123456Z",
    "state": "Scan",
    "type": "detect",
    "label": "nameplate",
    "roi": [0.2, 0.25, 0.6, 0.5],
    "boxes": [[100, 150, 200, 50]],
    "best_conf": 0.87,
    "phase": "Search for Monster"
  },
  {
    "ts": "2024-01-15T10:30:17.234567Z",
    "state": "PrimeTarget",
    "type": "click",
    "label": "prime_nameplate",
    "roi": [0.2, 0.25, 0.6, 0.5],
    "boxes": [],
    "best_conf": 0.0,
    "click": {
      "x": 250,
      "y": 175,
      "mode": "dry_run"
    },
    "phase": "Click on the Monster"
  }
]
```

#### Timeline Event Types
| Type | Description | Additional Fields |
|------|-------------|-------------------|
| `detect` | Detection result | `boxes`, `best_conf` |
| `confirm` | Secondary confirmation | `boxes`, `best_conf` |
| `click` | Click execution | `click` object |
| `transition` | State transition | `notes` (optional) |

### GET /api/diag
Returns diagnostic information about the bot's dependencies and versions.

#### Response
```json
{
  "cv2": "4.8.1",
  "numpy": "1.24.3",
  "mss": "9.0.1",
  "flask": "2.3.3",
  "tesseract": "5.3.3"
}
```

---

## Error Handling

### Common Error Responses

#### Window Not Found
```json
{
  "error": "Window not found: Brighter Shores"
}
```

#### Invalid Parameters
```json
{
  "error": "Invalid method: must be 'auto', 'template', or 'ocr'"
}
```

#### Tesseract Not Found
```json
{
  "error": "Tesseract executable not found at path: C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
}
```

### HTTP Status Codes
- `200 OK` - Success
- `204 No Content` - No data available
- `400 Bad Request` - Invalid request parameters
- `404 Not Found` - Endpoint not found
- `500 Internal Server Error` - Server error

---

## Usage Examples

### Starting Detection with OCR
```bash
curl -X POST http://127.0.0.1:8083/api/start \
  -H "Content-Type: application/json" \
  -d '{"word": "Wendigo", "method": "ocr"}'
```

### Monitoring Status
```bash
curl http://127.0.0.1:8083/api/status
```

### Getting Live Preview
```bash
curl -o preview.jpg http://127.0.0.1:8083/api/preview.jpg
```

### Streaming Logs
```bash
curl "http://127.0.0.1:8083/api/logs/tail?n=50"
```

---

## Rate Limiting
- No explicit rate limiting (localhost only)
- Runtime loop operates at ~2 FPS by default
- API calls are processed synchronously

## Timeouts
- Default request timeout: 30 seconds
- Long-running operations may block other requests

## WebSocket Support
Currently not implemented. All communication is via REST API.
