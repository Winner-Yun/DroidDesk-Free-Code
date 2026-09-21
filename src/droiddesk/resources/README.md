# resources/

- `icons/` — application and sidebar icons:
  - `logo.png` — application brand logo (240x240 PNG)
  - `droiddesk.ico` — multi-resolution Windows executable and window icon (16 to 256px)
- `qss/` — Qt stylesheets consumed by `ui/theme.py`
- `bin/` — bundled `gitleaks.exe` (the only external tool shipped in the
  installer per Section 3; everything else is discovered on the host per the
  ToolLocator chain in Section 3.1)
