# DroidDesk: User & Packaging Guide (PyInstaller)

This guide provides step-by-step instructions to:
1. **Run DroidDesk locally on your machine.**
2. **Build an `.exe` file using PyInstaller for other users.**
3. **(Optional) Create a Windows Setup Installer wizard using Inno Setup.**

---

## 1. Run DroidDesk on Your Device

### Prerequisites
- **Python 3.12+**
- **Android SDK Tools (`adb`, `aapt2`, `apksigner`)**:
  - Automatically found if Android Studio or Android SDK command-line tools are installed.
  - Can also be set in DroidDesk's **Settings** screen.
- **Gitleaks**:
  - Pre-bundled in `src/droiddesk/resources/bin/gitleaks.exe`.

### Steps
1. **Activate your virtual environment:**
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```
2. **Install requirements:**
   ```powershell
   pip install -r requirements.txt
   ```
3. **Launch DroidDesk:**
   ```powershell
   python -m droiddesk
   ```

---

## 2. Make an `.exe` Using PyInstaller

PyInstaller bundles the Python interpreter, PySide6, and all dependencies into a standalone folder. **End users do not need Python installed.**

### Step 1: Run the PyInstaller Build Script
In PowerShell (with your virtual environment active):
```powershell
python packaging/pyinstaller_build.py
```

### What This Does:
- Scans `src/droiddesk` and packages all code and dependencies.
- Embeds PySide6, Androguard, resources, icons, and templates.
- Generates the standalone folder at:
  ```
  dist\droiddesk\
  ```
  Inside this folder is `droiddesk.exe`.

---

## 3. How to Share with Other Users

### Option A: Portable ZIP (Fastest)
1. Compress the `dist\droiddesk` directory:
   ```powershell
   Compress-Archive -Path dist\droiddesk\* -DestinationPath dist\DroidDesk-portable.zip
   ```
2. Send `DroidDesk-portable.zip` to other users.
3. Users extract the ZIP to any folder and double-click `droiddesk.exe`.

---

### Option B: Windows Setup Installer Wizard (`.exe`)
To generate a single `DroidDesk-Setup-0.1.0.exe` installer with a setup wizard, desktop shortcuts, and `.apk` file associations:

1. Download and install [Inno Setup 6](https://jrsoftware.org/isdl.php).
2. Run Inno Setup Compiler from PowerShell:
   ```powershell
   & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging/installer.iss
   ```
   *(Or open `packaging/installer.iss` in the Inno Setup GUI and click **Build > Compile**).*
3. The installer is generated at:
   ```
   dist\installer\DroidDesk-Setup-0.1.0.exe
   ```
4. Send `DroidDesk-Setup-0.1.0.exe` to users.
