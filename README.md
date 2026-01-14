# 📂 File Organizer

![Platform](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/python-3.8%2B-blue?logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)

**File Organizer** is a comprehensive desktop application designed to eliminate file chaos. It automates file management tasks, allowing users to organize, rename, and move files efficiently to prevent data loss and clutter.

> **⬇️ Download the latest version for Windows:**
> ## [🌐 Visit Official Website & Download](https://fileorganizer.framer.website/)

## 🖼️ Screenshots

| Dashboard | Settings |
|:---:|:---:|
| ![Main Interface](bin/theme/Desktop.png) | ![Settings](bin/theme/Settings.png) |

## ✨ Key Features

* **Automation Engine:** Background monitoring of folders (using `watchdog`) to sort files instantly as they appear.
* **Smart Renaming:** Bulk rename files based on rules using regex and metadata.
* **System Tray Integration:** The app runs unobtrusively in the background (via `pystray`).
* **Advanced File Handling:**
    * Reads metadata from Audio (`mutagen`), PDF (`PyPDF2`), and Images (`Pillow`, `piexif`).
    * Secure deletion using `send2trash`.
* **Configurable Logic:** Behavior is fully customizable via JSON configuration files.
* **Windows Integration:** Native interaction using `win32gui` and `ctypes`.

## 💿 Installation & Usage

### 👤 For Users (Windows Executable)
You don't need to install Python. Just download the app and run it.

1.  Go to our **[Official Website](https://fileorganizer.framer.website/)**.
2.  Download the latest `FileOrganizer_setup.exe` (or `.zip`).
3.  Run the installer. The app will minimize to the system tray area.

---

### 👨‍💻 For Developers (Source Code)
If you want to contribute or run the raw Python code:

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/mailicynk/file-organaizer.git](https://github.com/mailicynk/file-organaizer.git)
    cd file-organizer
    ```

2.  **Create a virtual environment:**
    ```bash
    python -m venv venv
    venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Run the app:**
    ```bash
    python main.py
    ```

## 🛠️ Tech Stack

* **Language:** Python 3.x
* **GUI:** Tkinter (Custom styled)
* **Core Libraries:** `watchdog`, `pillow`, `mutagen`, `pymediainfo`, `PyPDF2`, `psutil`, `win32gui`, `pystray`.

## 📦 Building from Source

This project includes a PyInstaller spec file (`FileOrganizer.spec`). To build a standalone `.exe` file:

1.  Install PyInstaller:
    ```bash
    pip install pyinstaller
    ```
2.  Run the build command:
    ```bash
    pyinstaller FileOrganizer.spec
    ```
3.  The executable will appear in the `dist/` folder.

## 📂 Project Structure

```text
file-organizer/
├── bin/                   # Assets (Icons, Images)
├── back_function.py       # Backend logic & helper functions
├── main.py                # Entry point & GUI logic
├── FileOrganizer.spec     # PyInstaller build specification
├── sorting_profiles.json  # (Auto-generated) Sorting profiles
├── renaming_config.json   # (Auto-generated) Renaming profiles
├── desktop_config.json    # (Auto-generated) Desktop zones
├── automation_config.json # (Auto-generated) Automatization rules
├── vips_config.json       # (Auto-generated) Tracked files
├── settings_config.json   # (Auto-generated) App settings
└── README.md              # Documentation
```


## 👥 Development Team

This project was created by a team of 6 developers. Each member contributed to different aspects of the application:

| Developer | Role & Responsibilities | GitHub Profile |
|:---:|:---|:---:|
| <img src="https://github.com/teforteem79.png" width="50"> <br> **teforteem79** | **Backend / Tester** <br> File sorting, desktop organizing, debugging| [@teforteem79](https://github.com/teforteem79) |
| <img src="https://github.com/mailicynk.png" width="50"> <br> **mailicynk** | **Team lead / Dev** <br> PyInstaller build, File renaming, Background execution | [@mailicynk](https://github.com/mailicynk) |
| <img src="https://github.com/Kelner-r.png" width="50"> <br> **Kelner-r** | **Backend / Tester** <br> File system monitoring, algorithms | [@Kelner-r](https://github.com/Kelner-r) |
| <img src="https://github.com/omykytyn543.png" width="50"> <br> **omykytyn543** | **Backend / Designer** <br> Logs menu backend, design, website | [@omykytyn543](https://github.com/omykytyn543) |
| <img src="https://github.com/getmandoroshenko228.png" width="50"> <br> **getmandoroshenko228** | **Frontend / Designer** <br> Worked on creating a 2-menu interface, got a little carried away with setup design and researched how to host an executive | [@getmandoroshenko228](https://github.com/getmandoroshenko228) |
| <img src="https://github.com/romart008.png" width="50"> <br> **romart008** | **Product manager /  Frontend** <br> UI development, Config files logic, Backend and frontend linking | [@romart008](https://github.com/romart008) |
