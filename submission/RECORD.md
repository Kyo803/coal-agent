# Recording Coal without OBS

OBS usually shows a **black rectangle** for the Coal window on laptops with two
GPUs: WebView2 renders on the discrete GPU and OBS's default capture path reads
the integrated one. You do not need OBS.

## Option A — Xbox Game Bar (built in, best for one window)

1. Open Coal (`desktop\launcher\coal-launcher.exe`) and maximise the window.
2. Press **Win + G** once, pin the **Capture** widget, and enable the microphone.
3. Click the Coal window so it is focused.
4. Press **Win + Alt + R** to start. A small bar shows the timer and mic level.
5. Press **Win + Alt + R** again to stop.

Output: `%USERPROFILE%\Videos\Captures\` as `.mp4` (1080p30).
If Win+Alt+R does nothing, open Settings → Gaming → Captures and turn on
"Record what happened"/"Record game clips". If it says the app cannot be
recorded, use Option B.

## Option B — Snipping Tool (Windows 11, no extra app)

1. Press **Win + Shift + S**.
2. Switch the mode selector to **Video** (the camcorder icon).
3. Drag a box around the Coal window, press **Start**.
4. Stop from the toolbar; it opens in the Snipping Tool, then **Save as** `.mp4`.

This captures whatever is on screen, including GTKWave when it opens over Coal.

## Option C — fix OBS (only if you want OBS specifically)

1. Right-click OBS → **Run as administrator**.
2. Remove the old source. Add **Window Capture** (not Display Capture).
3. In the source properties, set **Capture Method** to
   `Windows 10 (1903 and up)` and pick the window titled
   `Coal - the AI that proves the chip works`.
4. If still black: Settings → Graphics → set OBS to **Power saving GPU**
   (the iGPU), restart OBS, and use Display Capture.
5. Output → Recording: MP4, 1920x1080, 30 fps, encoder x264.

## Option D — ffmpeg (full desktop, no GPU dependence)

```powershell
winget install Gyan.FFmpeg
ffmpeg -f gdigrab -framerate 30 -i desktop -c:v libx264 -preset veryfast `
       -crf 20 -pix_fmt yuv420p coal_demo.mp4
```

`gdigrab` is a GDI capture; if the Coal pane is black, use Option A or B.

## Before the take

- Warm the toolchain once, off camera:
  `cd agent; py -3.15 -c "import chipflow; chipflow.build_block('warmup','counter',width=8)"`
- Turn off notifications (Focus assist), close chat apps.
- 1920x1080, taskbar auto-hide, font size comfortable.
- Record a 10-second test and play it back **before** the real take.
- Keep [COMMAND_PACK.md](COMMAND_PACK.md) on a second screen.

## After

Trim the head/tail in Clipchamp or Photos, export 1080p, then upload to
YouTube or Vimeo as **public or unlisted, no password**, and put that URL in
the Devpost video field.
