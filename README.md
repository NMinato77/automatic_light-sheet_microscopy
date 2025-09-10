# Stage Scan Controller (Python + Tkin

A minimal GUI to automate tiled stage scans while driving a function generator for trigger output.  
Intended for microscope setups where a motorized stage is moved in X–Y tiles and a Rigol DG800-series generator outputs pulses during each Y scan.

## Hardware  
- Function generator for triggering: Rigol DG800-series
- - Connecting via USB
- Stage controller: OptoSigma SHOT-702
- - Connecting via COM port

## Features
- Set scan speeds (X/Y), Y travel distance, trigger frequency, number of X tiles, and X step.
- Manual “Go to XYZ” for stage positioning.
- Start / Stop / Next / Return buttons with progress bar and text log.
- Simple serial control for a stage and SCPI (VISA) control for a function generator.

## Requirements
- Python 3.9+  
- Packages:  
  ```bash
  pip install pyserial pyvisa
  ```
## Quick Start
```bash
python automatic_scan.py
```

1. Enter scan parameters (speeds in mm/s, Y distance in mm, frequency in Hz, tiles/step).  
2. Click **Start Scan**.  
3. After each tile finishes, click **Next Scan** to proceed.  
4. **Stop Scan** aborts outputs and motion.  
5. **Return to Start** moves stage back to the initial position (asks you to confirm lasers are off).

## UI Controls
- **Start Scan**: begins the scan sequence in a background thread.  
- **Next Scan**: advances to the next tile after a Y scan completes.  
- **Stop Scan**: turns off DG800 CH1 output and sends ESC to the stage; sets an internal stop flag.  
- **Return to Start**: moves back to stored `(x0, y0)` after confirmation.  
- **Go to XYZ**: manual absolute move to entered coordinates.

## Safety
- Ensure laser interlocks and shutters are **off** before any homing/return moves.  
- Verify soft limits and speed settings on the stage controller.  
- Test first with low speeds and small distances.

## Platform
- **Windows**: default COM port naming (`COM8`).
