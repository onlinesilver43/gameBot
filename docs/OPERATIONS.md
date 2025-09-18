# Operations Guide

This guide covers production deployment, monitoring, maintenance, and operational procedures for the Brighter Shores Bot.

## 🚀 Production Deployment

### Prerequisites
- Windows Server 2019+ or Windows 10/11 Pro
- Python 3.11+ installed
- Administrator privileges
- Stable internet connection
- Game client installed and configured

### Deployment Steps

#### 1. Environment Setup
```bash
# Clone repository
git clone <repository-url> C:\gameBot
cd C:\gameBot

# Setup production environment
.\scripts\setup.ps1 -PythonVersion 3.11

# Configure for production
# Edit config/profile.yml for production settings
```

#### 2. Production Configuration
```yaml
# config/profile.yml - Production Settings
window_title: "Brighter Shores"
monitor_index: 1
detection_method: "auto"
confidence_threshold: 0.75
log_level: "INFO"
debug_enabled: false

# Production safety settings
input_delay_ms: 200
scan_interval_ms: 500
action_timeout_ms: 10000
```

#### 3. Service Installation
Create a Windows service for automatic startup:

```powershell
# Create service script
$serviceScript = @"
# C:\gameBot\Start-GameBot.ps1
param([string]$Action = "start")

$botPath = "C:\gameBot"
$venvPath = "$botPath\.venv\Scripts\python.exe"
$serverScript = "$botPath\bsbot\ui\server.py"

switch ($Action) {
    "start" {
        Start-Process -FilePath $venvPath -ArgumentList $serverScript -WorkingDirectory $botPath
    }
    "stop" {
        Get-Process python | Where-Object {$_.Path -like "*gameBot*"} | Stop-Process
    }
}
"@

$serviceScript | Out-File "C:\gameBot\Start-GameBot.ps1"

# Create Windows service
New-Service -Name "GameBot" -BinaryPathName "powershell.exe -ExecutionPolicy Bypass -File C:\gameBot\Start-GameBot.ps1" -DisplayName "Brighter Shores Bot" -StartupType Automatic
```

#### 4. Firewall Configuration
```powershell
# Allow local connections only
New-NetFirewallRule -Name "GameBot-API" -DisplayName "GameBot API" -Direction Inbound -LocalPort 8083 -Protocol TCP -Action Allow -Profile Private
```

### 🚀 Startup Procedures

#### Automated Startup
```powershell
# Start service
Start-Service -Name "GameBot"

# Verify startup
Start-Sleep 5
curl http://127.0.0.1:8083/api/status
```

#### Manual Startup
```powershell
# Navigate to bot directory
cd C:\gameBot

# Activate environment and start
.\.venv\Scripts\activate
python -m bsbot.ui.server

# Or use convenience script
.\scripts\serve.ps1 -LogLevel INFO
```

## 📊 Monitoring & Alerting

### Health Checks

#### Automated Health Monitoring
```powershell
# Create health check script
$healthCheckScript = @"
# C:\gameBot\Health-Check.ps1
$status = curl -s http://127.0.0.1:8083/api/status | ConvertFrom-Json

if ($status.running -eq $false) {
    Write-Host "CRITICAL: Bot is not running" -ForegroundColor Red
    exit 1
}

if ($status.last_result.count -eq 0) {
    Write-Host "WARNING: No detections in last cycle" -ForegroundColor Yellow
}

Write-Host "OK: Bot is healthy" -ForegroundColor Green
"@

$healthCheckScript | Out-File "C:\gameBot\Health-Check.ps1"
```

#### Windows Task Scheduler Monitoring
```powershell
# Create scheduled task for health checks
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File C:\gameBot\Health-Check.ps1"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 365)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName "GameBot-HealthCheck" -Action $action -Trigger $trigger -Settings $settings -User "SYSTEM" -RunLevel Highest
```

### Key Metrics to Monitor

#### Performance Metrics
- **Detection Success Rate:** Percentage of frames with successful detections
- **Average Confidence:** Mean confidence score across detections
- **Frame Processing Time:** Time to process each frame
- **Memory Usage:** RAM consumption over time
- **CPU Usage:** Processor utilization

#### Operational Metrics
- **Uptime:** Service availability percentage
- **Error Rate:** Frequency of detection failures
- **Click Success Rate:** Percentage of successful input actions
- **False Positive Rate:** Incorrect detections per hour

### Log Analysis

#### Log Rotation
```powershell
# Configure log rotation
$logConfig = @"
# logging configuration
version: 1
disable_existing_loggers: false
formatters:
  default:
    format: '%(asctime)s %(levelname)s %(name)s: %(message)s'
handlers:
  file:
    class: logging.handlers.RotatingFileHandler
    filename: logs/app.log
    maxBytes: 10485760  # 10MB
    backupCount: 5
    formatter: default
root:
  level: INFO
  handlers: [file]
"@

$logConfig | Out-File "C:\gameBot\logging.yaml"
```

#### Log Monitoring Commands
```bash
# Recent errors
Get-Content C:\gameBot\logs\app.log | Select-String -Pattern "ERROR|CRITICAL" | Select-Object -Last 10

# Performance analysis
Get-Content C:\gameBot\logs\app.log | Select-String -Pattern "detect.*found=True" | Measure-Object

# Timeline analysis
Get-Content C:\gameBot\logs\app.log | Select-String -Pattern "transition" | Select-Object -Last 20
```

## 🔧 Maintenance Procedures

### Regular Maintenance Tasks

#### Daily Tasks
```powershell
# Backup logs and configurations
$backupDir = "C:\gameBot\backups\$(Get-Date -Format 'yyyy-MM-dd')"
New-Item -ItemType Directory -Path $backupDir -Force

Copy-Item "C:\gameBot\logs\app.log" "$backupDir\"
Copy-Item "C:\gameBot\config\*" "$backupDir\" -Recurse

# Clean old screenshots
Get-ChildItem "C:\gameBot\assets\images\*" -File | Where-Object LastWriteTime -lt (Get-Date).AddDays(-7) | Remove-Item
```

#### Weekly Tasks
```powershell
# Update dependencies
cd C:\gameBot
.\scripts\setup.ps1

# Verify all templates are accessible
Get-ChildItem "C:\gameBot\assets\templates\*" | ForEach-Object {
    if (!(Test-Path $_.FullName)) {
        Write-Warning "Missing template: $($_.Name)"
    }
}

# Check configuration validity
python -c "import yaml; yaml.safe_load(open('config/profile.yml'))"
```

#### Monthly Tasks
```powershell
# Performance review
# Analyze detection success rates
# Review error patterns
# Update templates if needed

# Security review
# Verify file permissions
# Check for unauthorized access
# Update dependencies for security patches
```

### Template Maintenance

#### Template Validation
```powershell
# Validate all templates
Get-ChildItem "C:\gameBot\assets\templates\*.png" | ForEach-Object {
    $template = $_.FullName
    python -c "
import cv2
import sys
img = cv2.imread('$template')
if img is None or img.size == 0:
    sys.exit(1)
print(f'Valid template: {img.shape}')
"
}
```

#### Template Updates
```powershell
# Update template from new screenshot
.\scripts\extract-template.ps1 -Screenshot "new_screenshot.png" -Template "assets/templates/updated_enemy.png"

# Test updated template
python -m bsbot.tools.detect_cli --test-window --template "assets/templates/updated_enemy.png"
```

## 🔒 Security Considerations

### Access Control
- Bot runs on localhost only (127.0.0.1:8083)
- No external network access required
- Windows firewall restricts access to local machine

### File Permissions
```powershell
# Secure bot directory
icacls "C:\gameBot" /grant "Administrators:(OI)(CI)F" /grant "SYSTEM:(OI)(CI)F"

# Restrict config files
icacls "C:\gameBot\config\*.yml" /grant "Administrators:F" /grant "SYSTEM:F" /remove "Users"
```

### Audit Logging
```yaml
# Enable security auditing
logging:
  version: 1
  handlers:
    security:
      class: logging.FileHandler
      filename: logs/security.log
      formatter: security
  loggers:
    security:
      level: INFO
      handlers: [security]
```

## 🚨 Incident Response

### Common Incidents

#### Bot Stops Responding
```powershell
# Quick diagnosis
curl http://127.0.0.1:8083/api/status

# Check process status
Get-Process python | Where-Object {$_.Path -like "*gameBot*"}

# Restart service
Restart-Service -Name "GameBot"
```

#### High Error Rate
```powershell
# Analyze recent errors
Get-Content C:\gameBot\logs\app.log | Select-String -Pattern "ERROR" | Select-Object -Last 20

# Check system resources
Get-Process python | Select-Object Name, CPU, Memory

# Restart in safe mode
.\scripts\serve.ps1 -ClickMode "dry_run"
```

#### Detection Failures
```powershell
# Test detection manually
python -m bsbot.tools.detect_cli --test-window --title "Brighter Shores"

# Check template validity
python -m bsbot.tools.detect_cli --test-window --template "assets/templates/test.png"

# Verify configuration
python -c "import yaml; print(yaml.safe_load(open('config/profile.yml')))"
```

### Emergency Procedures

#### Complete System Reset
```powershell
# Stop all processes
Stop-Service -Name "GameBot" -Force
Get-Process python | Stop-Process -Force

# Backup current state
Copy-Item "C:\gameBot" "C:\gameBot-backup-$(Get-Date -Format 'yyyyMMdd-HHmmss')" -Recurse

# Clean reinstall
Remove-Item "C:\gameBot\.venv" -Recurse -Force
Remove-Item "C:\gameBot\logs\*" -Recurse -Force
.\scripts\setup.ps1
.\scripts\serve.ps1
```

## 📈 Performance Optimization

### System Tuning

#### Windows Optimization
```powershell
# Disable visual effects
Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects" -Name "VisualFXSetting" -Value 2

# Adjust power plan
powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c  # High performance
```

#### Bot Optimization
```yaml
# config/profile.yml - Optimized settings
scan_interval_ms: 200      # Faster scanning
roi_width: 0.8            # Larger ROI for better coverage
roi_height: 0.6
confidence_threshold: 0.7  # Balanced accuracy/speed
detection_method: "auto"   # Adaptive detection
```

### Resource Monitoring

#### Performance Baselines
- **Normal CPU Usage:** 5-15%
- **Normal Memory Usage:** 200-500MB
- **Normal Detection Rate:** 2-5 detections per second
- **Normal Response Time:** <100ms per frame

#### Performance Troubleshooting
```powershell
# Monitor resource usage
Get-Counter -Counter "\Processor(_Total)\% Processor Time" -SampleInterval 1 -MaxSamples 10
Get-Counter -Counter "\Memory\Available MBytes" -SampleInterval 1 -MaxSamples 10

# Profile bot performance
python -c "
import time
start = time.time()
# Run performance test
duration = time.time() - start
print(f'Performance test took {duration:.2f}s')
"
```

## 🔄 Backup & Recovery

### Backup Strategy

#### Automated Backups
```powershell
# Create backup script
$backupScript = @"
# C:\gameBot\Backup.ps1
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupPath = \"C:\gameBot\backups\$timestamp\"

# Create backup directory
New-Item -ItemType Directory -Path $backupPath -Force

# Backup configurations
Copy-Item \"C:\gameBot\config\*\" \"$backupPath\config\\\" -Recurse

# Backup templates
Copy-Item \"C:\gameBot\assets\templates\*\" \"$backupPath\templates\\\" -Recurse

# Backup logs (last 7 days)
Get-ChildItem \"C:\gameBot\logs\*.log\" | Where-Object LastWriteTime -gt (Get-Date).AddDays(-7) |
    Copy-Item -Destination \"$backupPath\logs\\\"

Write-Host \"Backup completed: $backupPath\"
"@

$backupScript | Out-File "C:\gameBot\Backup.ps1"
```

#### Scheduled Backups
```powershell
# Schedule daily backups
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File C:\gameBot\Backup.ps1"
$trigger = New-ScheduledTaskTrigger -Daily -At "02:00"
Register-ScheduledTask -TaskName "GameBot-Backup" -Action $action -Trigger $trigger -User "SYSTEM"
```

### Recovery Procedures

#### Configuration Recovery
```powershell
# Restore from backup
$backupDir = "C:\gameBot\backups\20231201-020000"
Copy-Item "$backupDir\config\*" "C:\gameBot\config\" -Recurse -Force

# Validate configuration
python -c "import yaml; yaml.safe_load(open('config/profile.yml'))"
```

#### Full System Recovery
```powershell
# Stop services
Stop-Service -Name "GameBot"

# Restore from backup
$backupDir = "C:\gameBot\backups\20231201-020000"
Copy-Item "$backupDir\*" "C:\gameBot\" -Recurse -Force

# Reinstall dependencies
.\scripts\setup.ps1

# Restart services
Start-Service -Name "GameBot"
```

## 📋 Operational Checklists

### Startup Checklist
- [ ] Verify game client is running
- [ ] Check bot service status
- [ ] Validate API endpoints
- [ ] Monitor initial detections
- [ ] Verify click functionality (dry-run first)

### Shutdown Checklist
- [ ] Stop bot service gracefully
- [ ] Backup current session logs
- [ ] Close game client
- [ ] Verify no orphaned processes

### Maintenance Checklist
- [ ] Review error logs
- [ ] Update templates if needed
- [ ] Clean old backups
- [ ] Verify system resources
- [ ] Test backup recovery

---

## 📞 Support & Escalation

### Support Levels
1. **Level 1:** Basic troubleshooting and monitoring
2. **Level 2:** Configuration and template issues
3. **Level 3:** System performance and integration issues

### Escalation Procedures
1. Document the issue with full context
2. Attempt basic troubleshooting steps
3. Gather diagnostic information
4. Escalate with complete incident report

### Emergency Contacts
- **System Administrator:** [contact info]
- **Development Team:** [contact info]
- **Infrastructure Team:** [contact info]

---

*This document should be reviewed quarterly and updated as operational procedures evolve.*
