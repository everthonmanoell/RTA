# Safety-Critical Touch & Swipe Test Suite

Complete validation suite for safety-critical touch and swipe operations in the RTA execution controller.

## Overview

This test suite validates three critical safety flows:
1. **Pause-and-Listen Touch** - Real-time ADB feedback capture and validation
2. **Swipe Signal Monitoring** - Continuous signal continuity and pressure checks
3. **Metrics Recording** - Accurate capture of actual positions from app feedback

## Files

```
tests/
├── test_safety_critical_touch.py          # Unit tests (15+ test methods)
├── run_safety_integration_tests.py        # Integration test runner
└── README.md                              # This file
```

## Quick Start

### 1. Run Unit Tests

Test individual components in isolation:

```bash
# Run all unit tests
python -m pytest tests/test_safety_critical_touch.py -v

# Run specific test class
python -m pytest tests/test_safety_critical_touch.py::TestPauseAndListen -v

# Run with coverage
python -m pytest tests/test_safety_critical_touch.py --cov=drivers.device
```

**Expected Output:**
```
test_safety_critical_touch.py::TestPauseAndListen::test_touch_with_feedback_success PASSED
test_safety_critical_touch.py::TestPauseAndListen::test_touch_with_feedback_timeout PASSED
test_safety_critical_touch.py::TestPauseAndListen::test_touch_with_degraded_signal PASSED
...
========== 15 passed in 2.34s ==========
```

### 2. Run Integration Tests

Execute end-to-end scenarios with live device:

```bash
# With specific device
python tests/run_safety_integration_tests.py --device emulator-5554 --cycles 10

# With custom output directory
python tests/run_safety_integration_tests.py --device emulator-5554 --cycles 5 --log-dir ./my_results

# Full test suite (default: 5 cycles)
python tests/run_safety_integration_tests.py --device 192.168.1.100:5555
```

**Expected Output:**
```
======================================================================
SAFETY-CRITICAL INTEGRATION TEST SUITE
======================================================================

Starting TEST 1: Touch Feedback Capture (5 cycles)
  Cycle 1: PASS (0.213s)
  Cycle 2: PASS (0.195s)
  ...
  Summary: 5/5 passed

Starting TEST 2: Swipe Signal Monitoring (5 cycles)
  Cycle 1: PASS (signal: min=0.85, avg=0.92)
  ...
  Summary: 5/5 passed

Starting TEST 3: Pressure Bounds Validation (5 cycles)
  Cycle 1: PASS (pressure: 350-650g)
  ...
  Summary: 5/5 passed

Starting TEST 4: Metrics Recording Accuracy
  STATUS: PASS

======================================================================
TEST SUMMARY
======================================================================
  touch_feedback............................ ✓ PASS
  swipe_monitoring.......................... ✓ PASS
  pressure_bounds........................... ✓ PASS
  metrics................................... ✓ PASS
======================================================================
OVERALL: 4/4 test groups passed

Results saved to: test_results/safety_integration_results_1711000335.json
```

## Test Coverage

### Unit Tests (5 test classes)

#### TestPauseAndListen (3 tests)
- `test_touch_with_feedback_success` - Successful touch with ADB response
- `test_touch_with_feedback_timeout` - Timeout handling when ADB unavailable
- `test_touch_with_degraded_signal` - Touch succeeds but signal degraded

#### TestSwipeSafetyMonitoring (3 tests)
- `test_swipe_success_with_monitoring` - Successful swipe with continuous checks
- `test_swipe_fails_on_signal_loss` - Abort when signal drops mid-swipe
- `test_swipe_fails_on_excessive_pressure` - Abort when pressure exceeds bounds

#### TestMetricsRecording (2 tests)
- `test_touch_metrics_with_feedback` - Verify actual position recorded
- `test_swipe_metrics_with_safety_reason` - Verify failure reason captured

#### TestSignalValidation (2 tests)
- `test_signal_continuity_good` - Pass with strong signal
- `test_signal_continuity_degraded` - Fail with weak signal

#### TestPressureBounds (3 tests)
- `test_pressure_within_bounds` - Pass when in range
- `test_pressure_exceeds_max` - Fail when too high
- `test_pressure_below_min` - Fail when too low

### Integration Tests (4 scenarios)

1. **Touch Feedback Capture** - 5-10 cycles
   - Validates ADB feedback parsing
   - Checks timeout behavior
   - Confirms signal strength reporting

2. **Swipe Signal Monitoring** - 5-10 cycles
   - Validates continuous signal checks
   - Tests abort on signal loss
   - Confirms pressure validation

3. **Pressure Bounds Validation** - 5-10 cycles
   - Tests pressure within safe range
   - Validates warnings near limits
   - Confirms abort on violation

4. **Metrics Recording** - Single run
   - Validates metrics file creation
   - Checks structure and completeness
   - Verifies actual position capture

## Validation Checklist

Before merging to production, complete:

- [ ] All unit tests pass (`test_safety_critical_touch.py`)
- [ ] All integration tests pass with 10 cycles
- [ ] Feedback rate ≥ 95% in metrics
- [ ] Swipe success rate ≥ 90%
- [ ] No unexpected aborts in logs
- [ ] Device logs show proper ADB feedback
- [ ] Metrics files valid JSON
- [ ] Configuration parameters set correctly
- [ ] Safety design document reviewed

## Configuration

Required config in `config.py`:

```python
# Touch feedback parameters
TOUCH_PAUSE_DURATION_SEC = 0.3
TOUCH_FEEDBACK_TIMEOUT_SEC = 2.0

# Swipe safety monitoring
SWIPE_MONITOR_INTERVAL_MS = 50
SWIPE_SIGNAL_THRESHOLD = 0.7
SWIPE_SIGNAL_DROP_THRESHOLD = 0.2
SWIPE_PRESSURE_MIN_GRAMS = 300
SWIPE_PRESSURE_MAX_GRAMS = 700

# Pressure sensor calibration
PRESSURE_SENSOR_CALIBRATION = 1.0
```

## Troubleshooting

### ADB Connection Issues
```bash
# Check device connection
adb devices

# Reset ADB
adb kill-server
adb start-server

# Verify feedback listener
adb logcat -s RTA_FEEDBACK
```

### Timeout Errors
- Increase `TOUCH_FEEDBACK_TIMEOUT_SEC` (default 2.0 sec)
- Check network latency to device
- Verify app is running and responsive

### Signal Degradation Warnings
- Check screen cleanliness and sensor alignment
- Verify no electromagnetic interference
- Run pressure calibration test
- Review sensor logs in `/logs/rta_safety_critical.log`

### Pressure Out of Bounds
- Run pressure sensor calibration
- Check `PRESSURE_SENSOR_CALIBRATION` factor
- Verify robot Z-axis at correct height
- Review tactile feedback logs

## Logs & Results

All test outputs saved to: `test_results/`

**Files:**
- `safety_integration_results_*.json` - Detailed test results
- `rta_safety_critical.log` - Runtime logs (if integration tests run)

**Viewing Results:**
```bash
# Format JSON output
python -m json.tool test_results/safety_integration_results_*.json

# Check logs
tail -100f logs/rta_safety_critical.log
```

## Safety Case Alignment

This test suite provides evidence for:
- **Requirement RTA-SC-001**: Touch operations confirmed via app feedback
- **Requirement RTA-SC-002**: Signal continuity monitored during swipe
- **Requirement RTA-SC-003**: Pressure bounds enforced with abort capability
- **Requirement RTA-SC-004**: Metrics track actual positions from feedback

See [SAFETY_CRITICAL_DESIGN.txt](../SAFETY_CRITICAL_DESIGN.txt) for full safety case.

## Development Notes

### Adding New Tests
1. Create test method in appropriate test class
2. Use descriptive name: `test_<component>_<scenario>`
3. Include docstring explaining what's tested
4. Run tests to verify

### Modifying Integration Tests
1. Edit `run_safety_integration_tests.py` test method
2. Update simulation or validation logic
3. Adjust cycles/thresholds as needed
4. Re-run to verify

### Debugging Failures
```python
# Run specific test with verbose output
python -m pytest tests/test_safety_critical_touch.py::TestPauseAndListen::test_touch_with_feedback_success -vv

# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Check mock calls
mock_controller.touch_marker_with_pause_and_listen.assert_called_once()
call_args = mock_controller.touch_marker_with_pause_and_listen.call_args
```

## Support

For issues or questions:
1. Check [SAFETY_CRITICAL_DESIGN.txt](../SAFETY_CRITICAL_DESIGN.txt) for architecture details
2. Review test class docstrings for scenario explanations
3. Check integration test logs for runtime diagnostics
4. Verify device configuration and ADB connectivity
