# Developer Guide

This guide provides everything you need to start developing with the Brighter Shores Bot.

## 🚀 Quick Start

### Prerequisites
- **Windows 10/11** (required for Win32 APIs)
- **Python 3.11** (via `py` launcher)
- **PowerShell** (for automation scripts)
- **Git** (for version control)

### 1. Clone and Setup
```bash
git clone <repository-url>
cd gameBot

# Setup Python environment and dependencies
.\scripts\setup.ps1

# Start the development server
.\scripts\serve.ps1
```

### 2. Open in Browser
Navigate to `http://127.0.0.1:8083` to access the web interface.

### 3. First Test
Try the detection test utilities:
```bash
# Test OCR on a screenshot
python -m bsbot.tools.detect_cli --test-screenshot assets/images/sample.png --word "Wendigo"

# Test live window detection
python -m bsbot.tools.detect_cli --test-window --title "Brighter Shores"
```

## 🏗️ Development Environment

### Project Structure
```
bsbot/                    # Main package
├── core/                # Core utilities (config, logging)
├── platform/            # Platform-specific code (Windows, input, capture)
├── vision/              # Computer vision (OCR, templates, detection)
├── skills/              # Skill controllers (combat, future skills)
├── runtime/             # Runtime orchestration
├── ui/                  # Web interface
└── tools/               # Development utilities

scripts/                 # PowerShell automation
docs/                    # Documentation
config/                  # Configuration files
assets/                  # Templates and images
logs/                    # Runtime logs
```

### Development Workflow

#### 1. Create Feature Branch
```bash
git checkout -b feature/your-feature-name
```

#### 2. Make Changes
- Follow the existing code style and patterns
- Add tests for new functionality
- Update documentation as needed

#### 3. Test Your Changes
```bash
# Run the bot with your changes
.\scripts\serve.ps1

# Test specific functionality
python -m bsbot.tools.detect_cli --test-window

# Check documentation health
.\scripts\check-docs.ps1
```

#### 4. Commit and Push
```bash
git add .
git commit -m "feat: add your feature description"
git push origin feature/your-feature-name
```

#### 5. Create Pull Request
- Use the PR template
- Include screenshots/videos for UI changes
- Reference related issues

## 🛠️ Development Tools

### Core Development Scripts

#### Setup Environment
```bash
# Basic setup
.\scripts\setup.ps1

# Custom Python version
.\scripts\setup.ps1 -PythonVersion 3.10

# With Tesseract path
.\scripts\setup.ps1 -TesseractPath "C:\path\to\tesseract.exe"
```

#### Run Development Server
```bash
# Basic server
.\scripts\serve.ps1

# Custom port
.\scripts\serve.ps1 -Port 3000

# Debug logging
.\scripts\serve.ps1 -LogLevel DEBUG
```

#### Template Extraction
```bash
# Extract template from screenshot
.\scripts\extract-template.ps1 -Screenshot assets/images/sample.png -Template assets/templates/new_enemy.png
```

### Testing Utilities

#### Detection Testing
```bash
# Test OCR on screenshot
python -m bsbot.tools.detect_cli --test-screenshot path/to/screenshot.png --word "EnemyName"

# Test live window detection
python -m bsbot.tools.detect_cli --test-window --title "Game Window"

# Test with template
python -m bsbot.tools.detect_cli --test-window --template assets/templates/enemy.png
```

#### Template Creation
```bash
# Extract template from red-text screenshot
python -m bsbot.tools.detect_cli --save-template-from screenshot.png --template output.png
```

### Debugging Tools

#### View Logs
```bash
# Tail application logs
Get-Content logs/app.log -Tail 50 -Wait

# View logs via API
curl "http://127.0.0.1:8083/api/logs/tail?n=100"
```

#### Capture Debug Images
```bash
# Get live preview
curl -o debug.jpg "http://127.0.0.1:8083/api/preview.jpg"

# Test ROI capture
python -m bsbot.tools.detect_cli --test-window
# Creates: window_roi.png or window_roi.detected.png
```

## 📚 Key Concepts

### Detection Pipeline

The bot uses a multi-stage detection pipeline:

1. **Window Capture**: Uses `mss` to capture game window
2. **Region of Interest**: Applies configurable ROI filtering
3. **Detection Methods**:
   - **Template Matching**: Precise, fast, requires template images
   - **OCR**: Flexible, works with text variations, slower
   - **Auto**: Tries template first, falls back to OCR

### Skill Controllers

Skills are modular controllers that implement specific behaviors:

```python
class CombatController(SkillController):
    def process_frame(self, frame, ctx):
        # Detection logic
        result = self.detect_targets(frame)

        # Decision making
        if result.found:
            actions = self.plan_actions(result)

        # Action execution
        return result, annotated_frame
```

### State Machines

Combat and other skills use finite state machines:

```python
# States: Scan -> PrimeTarget -> AttackPanel -> Prepare -> Weapon -> BattleLoop
def advance_state(self, target_ready, attack_boxes, ...):
    if self._state == "Scan" and target_ready:
        self._transition("PrimeTarget")
```

## 🔧 Configuration

### Development Configuration
```yaml
# config/profile.yml
debug_enabled: true
log_level: "DEBUG"
save_screenshots: true
confidence_threshold: 0.8
```

### Custom Key Bindings
```yaml
# config/keys.yml
attack: "left_click"
special_attack: "right_click"
target_nearest: "tab"
```

### Monster Profiles
```yaml
# config/monsters/custom_enemy.yml
id: custom_enemy
name: "Custom Enemy"
word: "Enemy"
prefix: "Big"
attack_word: "Attack"
template: "assets/templates/custom.png"
```

## 🧪 Testing

### Unit Testing
```python
# Example test
def test_detection():
    # Setup
    detector = DetectionEngine()

    # Test
    result = detector.detect_word(test_image, "Wendigo")

    # Assert
    assert result.found == True
    assert result.confidence > 0.8
```

### Integration Testing
```python
# Test full pipeline
def test_combat_flow():
    runtime = DetectorRuntime()
    runtime.start(word="Wendigo")

    # Simulate frames
    for frame in test_frames:
        result, preview = runtime.process_frame(frame)
        assert result.found or not result.found  # Valid result
```

### Manual Testing Checklist
- [ ] OCR detection works with test images
- [ ] Template detection works with known templates
- [ ] Live window capture works
- [ ] API endpoints respond correctly
- [ ] Web interface loads and functions
- [ ] Hotkeys work as expected
- [ ] Error handling works properly

## 🚀 Advanced Development

### Adding New Skills

1. **Create Skill Controller**
```python
# bsbot/skills/fishing/controller.py
class FishingController(SkillController):
    name = "fishing"

    def process_frame(self, frame, ctx):
        # Fishing-specific detection logic
        bobber = self.detect_bobber(frame)
        if bobber.found:
            return self.plan_fishing_action(bobber), annotated_frame
        return {}, frame
```

2. **Register Skill**
```python
# In runtime/service.py
def _register_default_skills(self):
    self._skills["combat"] = CombatController(self)
    self._skills["fishing"] = FishingController(self)
```

3. **Add Configuration**
```yaml
# config/interfaces/fishing.yml
id: fishing
name: "Fishing Interface"
bobber_words:
  - "bobber"
  - "float"
```

### Adding New Detection Methods

1. **Create Detection Function**
```python
# bsbot/vision/detect.py
def detect_color_pattern(bgr, target_color, threshold=0.8):
    # Color-based detection logic
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, target_color, target_color)
    return analyze_mask(mask, threshold)
```

2. **Integrate into Pipeline**
```python
# In skill controller
if method == "color":
    result = detect_color_pattern(frame, self.target_color)
```

### Performance Optimization

#### Profiling
```python
import cProfile
cProfile.run('detection_function()', 'profile_output.prof')

# Analyze results
import pstats
p = pstats.Stats('profile_output.prof')
p.sort_stats('cumulative').print_stats(10)
```

#### Optimization Techniques
- Use numpy vectorized operations
- Cache expensive computations
- Optimize ROI sizes
- Use appropriate image formats

## 🔒 Security & Safety

### Development Safety
- Always test in dry-run mode first
- Use test windows/titles for development
- Implement proper error handling
- Log security-relevant events

### Input Safety
```python
# Safe input execution
def safe_click(x, y):
    # Check foreground window
    if not is_game_window_foreground():
        logger.warning("Game not in foreground, skipping click")
        return

    # Add random delay
    time.sleep(random.uniform(0.1, 0.3))

    # Execute click
    human_click((x, y))
```

## 📊 Monitoring & Debugging

### Key Metrics to Monitor
- Detection confidence scores
- Frame processing time
- Memory usage
- Error rates
- Success rates

### Debug Logging
```python
# Enable debug logging
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# Log with context
logger.debug(f"Detection result: found={result.found}, conf={result.confidence}")
```

### Performance Profiling
```python
import time
start = time.time()
result = expensive_operation()
duration = time.time() - start
logger.info(f"Operation took {duration:.3f}s")
```

## 🤝 Contributing

### Code Style
- Follow PEP 8 Python style guide
- Use type hints for function parameters and return values
- Add docstrings to all public functions
- Use descriptive variable names

### Documentation Standards
- Update relevant docs with code changes
- Add examples for new features
- Keep API documentation current
- Test documentation examples

### Pull Request Process
1. **Branch**: Create feature branch from `main`
2. **Commits**: Use conventional commit format
3. **Tests**: Add tests for new functionality
4. **Docs**: Update documentation
5. **Review**: Request review from other developer
6. **Merge**: Squash merge after approval

### Commit Message Format
```
type(scope): description

[optional body]

[optional footer]
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

## 🔧 Troubleshooting Development Issues

### Common Issues

#### Import Errors
```bash
# Reinstall dependencies
.\scripts\setup.ps1

# Check Python path
python -c "import sys; print(sys.path)"
```

#### Detection Not Working
```bash
# Test with debug images
python -m bsbot.tools.detect_cli --test-screenshot debug.png --word "Test"

# Check confidence threshold
# Lower threshold in config/profile.yml
confidence_threshold: 0.6
```

#### Web Interface Not Loading
```bash
# Check if server is running
netstat -ano | findstr :8083

# Restart server
.\scripts\serve.ps1 -Port 8083
```

#### Template Issues
```bash
# Extract new template
.\scripts\extract-template.ps1 -Screenshot screenshot.png -Template template.png

# Test template
python -m bsbot.tools.detect_cli --test-window --template template.png
```

### Getting Help
1. Check existing documentation
2. Review recent commits for similar changes
3. Test with minimal reproduction case
4. Include full error logs when reporting issues

## 📈 Learning Resources

### Recommended Reading
- [OpenCV Documentation](https://docs.opencv.org/)
- [PyTesseract Documentation](https://pypi.org/project/pytesseract/)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [Computer Vision Fundamentals](https://www.pyimagesearch.com/)

### Community Resources
- Project issue tracker
- Development discussions
- Code review feedback
- Architecture decision records

---

## 🎯 Next Steps

1. **Get familiar** with the codebase structure
2. **Run the examples** in this guide
3. **Try modifying** a simple feature
4. **Add tests** for your changes
5. **Update documentation** as needed

Remember: Start small, test often, and document as you go! 🚀
