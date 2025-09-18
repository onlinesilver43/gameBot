# Implementation Guide

*Essential patterns and code examples for implementing bot features*

---

## 🎯 Core Implementation Patterns

### 1. Detection Implementation

```python
# Pattern: Feature Detection with Validation
def detect_feature(frame: np.ndarray, config: FeatureConfig) -> DetectionResult:
    """Detect feature in game frame with validation.

    Args:
        frame: BGR image from game capture
        config: Feature-specific configuration

    Returns:
        DetectionResult with validated detection data
    """
    # Preprocessing
    processed = preprocess_frame(frame, config.roi)

    # Feature detection
    raw_result = detection_algorithm(processed, config.threshold)

    # Validation and filtering
    validated = validate_detection(raw_result, config.constraints)

    return DetectionResult(
        found=validated.found,
        bbox=validated.bbox,
        confidence=validated.confidence,
        method=config.method,
        metadata=validated.metadata
    )
```

### 2. State Machine Controller

```python
# Pattern: State Machine for Complex Features
class FeatureController(SkillController):
    """State machine controller for multi-step features.

    States:
        scan -> detect -> process -> complete
    """

    def __init__(self, runtime):
        super().__init__(runtime)
        self._state = "scan"
        self._state_data = {}

    def process_frame(self, frame: np.ndarray, ctx: FrameContext) -> Tuple[Dict, Optional[bytes]]:
        """Process frame according to current state."""

        if self._state == "scan":
            return self._handle_scan(frame, ctx)
        elif self._state == "detect":
            return self._handle_detect(frame, ctx)
        elif self._state == "process":
            return self._handle_process(frame, ctx)

        return {}, None

    def _handle_scan(self, frame: np.ndarray, ctx: FrameContext) -> Tuple[Dict, Optional[bytes]]:
        """Scan for feature presence."""
        detection = self.detect_feature(frame)

        if detection.found:
            self._transition("detect")
            return self._create_result(detection), self._annotate_frame(frame, detection)

        return self._create_result(detection), None
```

### 3. Configuration Management

```python
# Pattern: Configuration with Validation
@dataclass
class FeatureConfig:
    """Validated configuration for feature."""
    enabled: bool = True
    threshold: float = 0.8
    roi: Tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    cooldown_ms: int = 1000

    def __post_init__(self):
        """Validate configuration after initialization."""
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError("Threshold must be between 0.0 and 1.0")

        if not all(0.0 <= coord <= 1.0 for coord in self.roi):
            raise ValueError("ROI coordinates must be between 0.0 and 1.0")

# Usage
config = FeatureConfig(threshold=0.9, roi=(0.2, 0.3, 0.6, 0.4))
```

---

## 🔧 Essential Utilities

### Frame Processing

```python
# Convert ROI coordinates to pixel coordinates
def roi_to_pixels(roi: Tuple[float, float, float, float],
                  window_size: Tuple[int, int]) -> Tuple[int, int, int, int]:
    """Convert normalized ROI to pixel coordinates."""
    x, y, w, h = roi
    win_w, win_h = window_size

    px = int(x * win_w)
    py = int(y * win_h)
    pw = int(w * win_w)
    ph = int(h * win_h)

    return px, py, pw, ph

# Extract ROI from frame
def extract_roi(frame: np.ndarray, roi: Tuple[int, int, int, int]) -> np.ndarray:
    """Extract region of interest from frame."""
    x, y, w, h = roi
    return frame[y:y+h, x:x+w].copy()
```

### Input Handling

```python
# Safe click with validation
def safe_click(x: int, y: int, hwnd: int, cooldown_ms: int = 200) -> bool:
    """Execute safe click with validation."""
    # Check if window is focused
    if not is_window_focused(hwnd):
        logger.warning("Target window not focused, skipping click")
        return False

    # Check cooldown
    if not check_cooldown("click", cooldown_ms):
        return False

    # Execute click with jitter
    jitter_x, jitter_y = get_human_jitter()
    actual_x = x + jitter_x
    actual_y = y + jitter_y

    return execute_click(actual_x, actual_y, hwnd)
```

### Logging Patterns

```python
# Structured logging for detections
def log_detection(result: DetectionResult, context: str):
    """Log detection results with context."""
    if result.found:
        logger.info(
            f"{context} | found=True count={len(result.boxes)} "
            f"conf={result.confidence:.3f} method={result.method}"
        )
    else:
        logger.debug(f"{context} | found=False method={result.method}")

# Timeline event logging
def emit_timeline_event(etype: str, label: str, data: Dict):
    """Emit structured timeline event."""
    event = {
        "ts": datetime.utcnow().isoformat(),
        "type": etype,
        "label": label,
        "data": data
    }
    logger.info(f"event | {json.dumps(event)}")
```

---

## 🎮 Game-Specific Patterns

### Combat Sequence

```python
# Pattern: Combat State Machine
class CombatController(SkillController):
    """Combat engagement state machine."""

    def __init__(self, runtime):
        super().__init__(runtime)
        self._state = "scan"
        self._last_attack_time = 0

    def process_frame(self, frame, ctx):
        detection = self.detect_combat_elements(frame)

        if self._state == "scan":
            if detection.target_found:
                self._start_engagement(detection.target_pos)
                self._state = "approach"

        elif self._state == "approach":
            if detection.can_attack:
                self._execute_attack()
                self._state = "attack"

        elif self._state == "attack":
            if detection.combat_ended:
                self._state = "scan"

        return self._create_combat_result(detection), self._annotate_frame(frame, detection)
```

### Resource Gathering

```python
# Pattern: Resource Node Detection and Interaction
class GatheringController(SkillController):
    """Resource gathering with pathfinding."""

    def __init__(self, runtime):
        super().__init__(runtime)
        self._current_target = None
        self._gather_path = []

    def process_frame(self, frame, ctx):
        # Detect available nodes
        nodes = self.detect_resource_nodes(frame)

        if not self._current_target and nodes:
            self._current_target = self.select_best_node(nodes)
            self._gather_path = self.calculate_path_to_node(self._current_target)

        if self._current_target:
            if self.at_node_location():
                self.interact_with_node()
                self._current_target = None
            else:
                self.move_along_path()

        return self._create_gathering_result(nodes), self._annotate_frame(frame, nodes)
```

---

## 🔄 Integration Patterns

### With Runtime System

```python
# Pattern: Runtime Integration
def integrate_with_runtime(runtime: DetectorRuntime, config: Dict) -> SkillController:
    """Create and configure controller for runtime integration."""

    # Create controller
    controller = FeatureController(runtime)

    # Apply configuration
    controller.configure(config)

    # Register with runtime
    runtime.register_skill("feature", controller)

    return controller

# Usage in server
@app.post("/api/start")
def start_feature():
    config = request.get_json()
    controller = integrate_with_runtime(rt, config)

    rt.start(skill="feature", **config)
    return jsonify({"ok": True})
```

### With Configuration System

```python
# Pattern: Configuration Loading
def load_feature_config(monster_id: str, interface_id: str) -> FeatureConfig:
    """Load and merge feature configuration."""

    # Load monster profile
    monster_config = load_monster_profile(monster_id)

    # Load interface profile
    interface_config = load_interface_profile(interface_id)

    # Load global settings
    global_config = load_profile()

    # Merge configurations
    return FeatureConfig(
        threshold=monster_config.get("threshold", global_config.confidence_threshold),
        roi=monster_config.get("roi", global_config.roi),
        cooldown_ms=interface_config.get("cooldown", 1000)
    )
```

---

## 🧪 Testing Patterns

### Unit Test Structure

```python
# Pattern: Component Testing
def test_feature_detection():
    """Test feature detection logic."""
    # Setup
    config = FeatureConfig(threshold=0.8)
    detector = FeatureDetector(config)

    # Mock frame
    frame = create_test_frame()

    # Execute
    result = detector.detect(frame)

    # Verify
    assert result.found == True
    assert result.confidence >= config.threshold
    assert result.bbox is not None

def test_state_transitions():
    """Test state machine transitions."""
    controller = FeatureController(mock_runtime)

    # Test transition logic
    controller._state = "scan"
    controller.process_frame(detection_frame, context)

    assert controller._state == "detect"
```

### Integration Test Pattern

```python
# Pattern: End-to-End Testing
def test_feature_integration():
    """Test complete feature workflow."""
    # Setup runtime
    runtime = DetectorRuntime()
    config = {"threshold": 0.8, "roi": [0.2, 0.3, 0.6, 0.4]}

    # Start feature
    runtime.start(skill="feature", **config)

    # Simulate frames
    for test_frame in test_frames:
        result, preview = runtime.process_frame(test_frame, context)
        assert result is not None

    # Verify final state
    assert runtime.get_status().running == True
```

---

## 🚨 Error Handling Patterns

### Graceful Degradation

```python
# Pattern: Fail-Safe Operation
def safe_process_frame(frame: np.ndarray, ctx: FrameContext) -> Tuple[Dict, Optional[bytes]]:
    """Process frame with comprehensive error handling."""
    try:
        # Primary processing
        result = self.process_frame_core(frame, ctx)

        if result.get("error"):
            # Fallback processing
            result = self.fallback_processing(frame, ctx)

        return result, self.annotate_frame(frame, result)

    except Exception as e:
        logger.exception("Frame processing failed")

        # Return safe default
        return {
            "error": str(e),
            "found": False,
            "method": "failed"
        }, None
```

### Validation Layers

```python
# Pattern: Input Validation
def validate_frame_input(frame: np.ndarray, ctx: FrameContext) -> bool:
    """Validate frame processing inputs."""
    if frame is None or frame.size == 0:
        logger.error("Invalid frame: None or empty")
        return False

    if not isinstance(ctx, FrameContext):
        logger.error("Invalid context type")
        return False

    if ctx.roi_size[0] <= 0 or ctx.roi_size[1] <= 0:
        logger.error("Invalid ROI size")
        return False

    return True
```

---

## 📊 Performance Patterns

### Optimization Techniques

```python
# Pattern: Efficient Processing
def optimize_frame_processing(frame: np.ndarray) -> np.ndarray:
    """Optimize frame for processing."""
    # Resize if too large
    if frame.shape[1] > 1920:
        scale = 1920 / frame.shape[1]
        frame = cv2.resize(frame, None, fx=scale, fy=scale)

    # Convert to grayscale once
    if self.use_grayscale:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    return frame

# Pattern: Caching Results
class CachedDetector:
    """Detector with result caching."""

    def __init__(self, cache_ttl_ms: int = 1000):
        self._cache = {}
        self._cache_ttl = cache_ttl_ms

    def detect_cached(self, frame_hash: str, frame: np.ndarray) -> DetectionResult:
        """Detect with caching."""
        now = time.time() * 1000

        if frame_hash in self._cache:
            cached_time, cached_result = self._cache[frame_hash]
            if now - cached_time < self._cache_ttl:
                return cached_result

        # Compute new result
        result = self.detect(frame)
        self._cache[frame_hash] = (now, result)

        return result
```

---

## 🔗 Cross-Component Integration

### Data Flow Coordination

```python
# Pattern: Component Communication
class ComponentCoordinator:
    """Coordinates data flow between components."""

    def __init__(self):
        self._components = {}
        self._data_bus = {}

    def register_component(self, name: str, component):
        """Register component for coordination."""
        self._components[name] = component

    def publish_data(self, source: str, data: Dict):
        """Publish data to other components."""
        self._data_bus[source] = data

        # Notify interested components
        for name, component in self._components.items():
            if hasattr(component, 'on_data_update'):
                component.on_data_update(source, data)

    def get_shared_data(self, component_name: str) -> Dict:
        """Get data shared by component."""
        return self._data_bus.get(component_name, {})
```

---

*This guide provides the essential implementation patterns needed for bot development. For API specifications and configuration schemas, see AI_CONTEXT.md. For human-readable tutorials, see other documentation files.*
