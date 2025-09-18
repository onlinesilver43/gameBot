# AI Context Guide

*Primary audience: AI assistants and automated systems*
*Purpose: Provide structured context for understanding the Brighter Shores Bot codebase*

---

## 🤖 AI-First Documentation Design

This documentation is structured for efficient AI consumption while remaining human-readable. Focus on:

- **Structured Information**: Clear hierarchies and consistent formatting
- **Minimal Context**: Essential information without redundancy
- **Machine-Readable**: Structured data that AI can parse efficiently
- **Actionable Insights**: Code examples and implementation patterns

---

## 📋 System Overview

### Core Architecture
```
Brighter Shores Bot
├── Platform Layer (Win32, Capture, Input)
├── Vision Layer (OCR, Template Matching, Detection)
├── Runtime Layer (Orchestration, State Management)
├── Skills Layer (Combat, Fishing, Woodcutting)
└── UI Layer (Web Interface, API)
```

### Key Components
| Component | Purpose | Key Files |
|-----------|---------|-----------|
| `bsbot/platform/` | OS integration, capture, input | `window.py`, `capture.py`, `input.py` |
| `bsbot/vision/` | Image processing, detection | `detect.py`, `templates.py` |
| `bsbot/runtime/` | Execution orchestration | `service.py` |
| `bsbot/skills/` | Game-specific logic | `combat/controller.py` |
| `bsbot/ui/` | Web interface | `server.py` |

---

## 🔧 Implementation Patterns

### Detection Pipeline
```python
# Standard pattern for all detection methods
def detect_feature(frame: np.ndarray) -> DetectionResult:
    """Detect feature in game frame.

    Args:
        frame: BGR image from game capture

    Returns:
        DetectionResult with bbox, confidence, method
    """
    # 1. Preprocessing
    processed = preprocess_frame(frame)

    # 2. Detection algorithm
    result = detection_algorithm(processed)

    # 3. Post-processing & validation
    validated = validate_result(result)

    return validated
```

### State Machine Pattern
```python
class FeatureController(SkillController):
    """State machine for feature implementation.

    States: [list of states]
    Transitions: [state -> condition -> next_state]
    """

    def __init__(self, runtime):
        super().__init__(runtime)
        self._state = "initial_state"

    def process_frame(self, frame, ctx):
        # State-specific processing
        if self._state == "detecting":
            return self._handle_detection(frame, ctx)
        elif self._state == "processing":
            return self._handle_processing(frame, ctx)
```

### Configuration Pattern
```python
@dataclass
class FeatureConfig:
    """Configuration for feature.

    Attributes:
        enabled: Whether feature is active
        threshold: Detection confidence threshold
        roi: Region of interest [x, y, w, h]
    """
    enabled: bool = True
    threshold: float = 0.8
    roi: Tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
```

---

## 📊 Data Structures

### Detection Result
```python
@dataclass
class DetectionResult:
    """Standard detection result format.

    Attributes:
        found: Whether target was detected
        bbox: Bounding box [x, y, w, h] or None
        confidence: Detection confidence 0.0-1.0
        method: Detection method used
        metadata: Additional method-specific data
    """
    found: bool
    bbox: Optional[Tuple[int, int, int, int]]
    confidence: float
    method: str
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### Frame Context
```python
@dataclass
class FrameContext:
    """Context information for frame processing.

    Attributes:
        hwnd: Window handle for input targeting
        window_rect: Window position [x, y, w, h]
        roi_origin: ROI offset from window [x, y]
        roi_size: ROI dimensions [w, h]
    """
    hwnd: int
    window_rect: Tuple[int, int, int, int]
    roi_origin: Tuple[int, int]
    roi_size: Tuple[int, int]
```

---

## 🔌 API Specifications

### REST Endpoints
```
GET  /api/status     - System status and configuration
POST /api/start      - Start detection with parameters
POST /api/pause      - Pause detection
POST /api/stop       - Stop detection
GET  /api/preview.jpg- Current frame preview
GET  /api/logs/tail  - Recent log entries
GET  /api/diag       - System diagnostics
GET  /api/timeline   - Event timeline
```

### Status Response Schema
```json
{
  "running": "boolean",
  "paused": "boolean",
  "last_result": {
    "found": "boolean",
    "count": "integer",
    "confidence": "number",
    "method": "string",
    "boxes": "array",
    "attack": "object",
    "special_attacks": "object",
    "weapon_1": "object",
    "planned_clicks": "array",
    "total_detections": "integer",
    "roi": "array",
    "state": "string"
  },
  "title": "string",
  "word": "string",
  "prefix_word": "string|null",
  "monster_id": "string",
  "interface_id": "string",
  "phase": "string|null",
  "template": "string|null",
  "method": "string",
  "click_mode": "string",
  "skill": "string"
}
```

---

## ⚙️ Configuration Schema

### Profile Configuration
```yaml
# config/profile.yml
window_title: "string"           # Target window title
detection_method: "auto|template|ocr"  # Detection method
confidence_threshold: "number"   # 0.0-1.0
roi: "array"                     # [x, y, w, h] as fractions 0.0-1.0
input_delay_ms: "integer"        # Delay between inputs
scan_interval_ms: "integer"      # Scan frequency
```

### Monster Profile
```yaml
# config/monsters/*.yml
id: "string"                     # Unique identifier
name: "string"                   # Human-readable name
word: "string"                   # Primary OCR target
prefix: "string|null"            # Secondary OCR target
attack_word: "string"            # Attack button text
template: "string|null"          # Template image path
```

---

## 🏗️ Implementation Guidelines

### Code Style
- Use type hints for all function parameters and return values
- Include docstrings with Args/Returns sections
- Follow naming conventions: `snake_case` for functions, `PascalCase` for classes
- Use dataclasses for data structures
- Handle exceptions explicitly

### Error Handling
```python
try:
    result = risky_operation()
except SpecificException as e:
    logger.error(f"Operation failed: {e}")
    return fallback_value
except Exception as e:
    logger.exception("Unexpected error")
    raise
```

### Logging
```python
# Use appropriate log levels
logger.debug("Detailed diagnostic information")
logger.info("Important state changes")
logger.warning("Potential issues")
logger.error("Errors that don't stop execution")
logger.critical("Critical failures")
```

### Testing
```python
def test_feature():
    # Setup
    component = FeatureUnderTest()

    # Execute
    result = component.process(input_data)

    # Verify
    assert result.expected_property == expected_value
    assert result.confidence > threshold
```

---

## 🔍 Key Integration Points

### With Game Window
- Capture via `mss` library
- Input via Win32 API
- Window focus detection
- DPI awareness

### With Computer Vision
- OpenCV for image processing
- Tesseract for OCR
- Template matching with NMS
- Color space conversions

### With Web Interface
- Flask for REST API
- JSON for data exchange
- JPEG streaming for previews
- WebSocket for real-time updates

---

## 🚨 Common Patterns & Anti-Patterns

### ✅ Good Patterns
- Use context managers for resource management
- Validate inputs at function boundaries
- Return structured results instead of raw values
- Document side effects in docstrings
- Use dependency injection for testability

### ❌ Anti-Patterns
- Global state mutations
- Hard-coded file paths
- Synchronous I/O in performance-critical paths
- Mixed concerns in single functions
- Silent error handling

---

## 📈 Performance Considerations

### Optimization Targets
- Frame processing: <100ms per frame
- Memory usage: <500MB steady state
- CPU usage: <20% average
- Detection accuracy: >90% for configured targets

### Profiling Points
- Image preprocessing time
- Detection algorithm performance
- Memory allocation patterns
- I/O operation frequency

---

## 🔧 Development Workflow

### For AI Assistants
1. **Understand Context**: Read this AI_CONTEXT.md first
2. **Identify Component**: Determine which layer/component is relevant
3. **Check Examples**: Look at IMPLEMENTATION.md for code patterns
4. **Validate Changes**: Run tests and check integration points

### For Code Changes
1. **Update Documentation**: Modify relevant .md files
2. **Add Tests**: Include unit tests for new functionality
3. **Check Integration**: Verify API contracts and data formats
4. **Validate Performance**: Ensure changes don't break performance targets

---

*This document provides the essential context AI needs to work effectively with the Brighter Shores Bot codebase. For human-readable documentation with tutorials and examples, see the other .md files in this directory.*
