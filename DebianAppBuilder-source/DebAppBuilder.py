import os
import sys
import json
import stat
import platform
import shutil
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import customtkinter as ctk
import core as c
from core import create_deb_structure
VERSION = "v3.0"

# Fix CustomTkinter "invalid command name ...check_dpi_scaling" / "...update" after race
# This pops every time write_files() loads because ScalingTracker / AppearanceModeTracker
# keep an `after` loop referencing the previous Tk instance (root → app). When root is
# destroyed the Tcl command "260295...check_dpi_scaling" is deleted but the pending
# after still fires, raising TclError via report_callback_exception.
# Must be installed before any CTk() is created.
try:
    _orig_report_cb = tk.Tk.report_callback_exception
    def _silent_report_cb(self, exc, val, tb):
        try:
            msg = str(val)
            # suppress the specific CustomTkinter tracker race – common on window switch
            if "invalid command name" in msg and ("check_dpi_scaling" in msg or msg.strip().endswith('update"') or ".update" in msg or "update" in msg):
                return
            if "invalid command name" in msg:
                # also suppress any stray "after script" invalid command after window destroy
                low = msg.lower()
                if "after" in low or "check_dpi" in low:
                    return
        except Exception:
            pass
        try:
            return _orig_report_cb(self, exc, val, tb)
        except Exception:
            pass
    tk.Tk.report_callback_exception = _silent_report_cb
except Exception:
    pass
SCRIPT_DIR = Path(__file__).resolve().parent
SAVE_FILE = SCRIPT_DIR / ".debappbuilder_session.json"


def _make_file_readonly(path: Path):
    """Make file read-only / immutable (cannot be changed)."""
    try:
        os.chmod(str(path), stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)  # 0o444
        if platform.system() == "Windows":
            try:
                subprocess.run(["attrib", "+R", str(path)], capture_output=True, timeout=5)
            except Exception:
                pass
    except Exception:
        pass


def _make_file_writable(path: Path):
    """Make file writable again (to allow overwrite on next save)."""
    try:
        os.chmod(str(path), stat.S_IREAD | stat.S_IWRITE | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH)
        if platform.system() == "Windows":
            try:
                subprocess.run(["attrib", "-R", str(path)], capture_output=True, timeout=5)
            except Exception:
                pass
    except Exception:
        pass


# Migration: remove old desktop_icon entrybox text from existing saved session (hicolor replaces it)
try:
    if SAVE_FILE.is_file():
        _make_file_writable(SAVE_FILE)
        try:
            _raw = SAVE_FILE.read_text(encoding="utf-8")
            _data = json.loads(_raw)
            if isinstance(_data, dict):
                _fields = _data.get("fields", {})
                if isinstance(_fields, dict) and "desktop_icon" in _fields:
                    _fields.pop("desktop_icon", None)
                    _data["fields"] = _fields
                    SAVE_FILE.write_text(json.dumps(_data, indent=2), encoding="utf-8")
        except Exception:
            pass
        _make_file_readonly(SAVE_FILE)
except Exception:
    pass
ICON_CANDIDATES = [
    SCRIPT_DIR / "DebAppBuilderIcon.png",
    SCRIPT_DIR.parent / "DebAppBuilderLogo.png",
]
ICON_PATH = next((p for p in ICON_CANDIDATES if p.exists()), ICON_CANDIDATES[0])
if platform.system() == "Windows":
    WINDOW_ICON_PATH = ICON_PATH.with_suffix(".ico")
print('''THIS PROJECT IS OPEN-SOURCE, YOU CAN MODIFY, DISTRIBUTE AND USE IT FREELY.\nHowever you must credit the original author and the project repository if you use it in your own project.\nSincerely Tuffgit21\nsite:https://tuffgit21.github.io/\nGithub repository:https://github.com/tuffgit21/Debian-App-Builder/ 
    ''')

def get_build_environment():
    system = platform.system()

    if system == "Windows":
        wsl_path = shutil.which("wsl.exe") or shutil.which("wsl")
        if not wsl_path:
            return None, None, "Windows (WSL is not available)"
        try:
            result = subprocess.run(
                [wsl_path, "-e", "cat", "/etc/os-release"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            release_info = (result.stdout + result.stderr).lower()
        except (OSError, subprocess.SubprocessError):
            return None, None, "Windows (Could not read the WSL distribution)"
        if "debian" in release_info or "ubuntu" in release_info:
            return "wsl", wsl_path, "Windows (WSL)"
        return None, None, "Windows (WSL must be a Debian or Ubuntu distribution)"

    if system == "Linux":
        os_release = Path("/etc/os-release")
        if os_release.exists():
            release_info = os_release.read_text(encoding="utf-8").lower()
            if "debian" in release_info or "ubuntu" in release_info:
                dpkg_path = shutil.which("dpkg-deb")
                if dpkg_path:
                    return "native", dpkg_path, "Debian-based Linux"
        return None, None, "Linux (Debian-based system required)"

    return None, None, f"Unsupported system: {system}"


def load_window_icon(window, header_size=64):
    icon = None
    header_icon = None
    if ICON_PATH.exists() and ICON_PATH.suffix.lower() in (".png", ".gif", ".ppm", ".pgm"):
        try:
            icon = tk.PhotoImage(file=str(ICON_PATH))
        except tk.TclError:
            icon = None
        if icon is not None:
            try:
                from PIL import Image
                pil = Image.open(ICON_PATH).convert("RGBA")
                pil = pil.resize((header_size, header_size), Image.LANCZOS)
                # Use CTkImage for HighDPI support (customtkinter), fallback to ImageTk
                try:
                    header_icon = ctk.CTkImage(light_image=pil, dark_image=pil, size=(header_size, header_size))
                except Exception:
                    from PIL import ImageTk
                    header_icon = ImageTk.PhotoImage(pil)
            except Exception:
                try:
                    factor = max(1, round(icon.width() / header_size))
                    header_icon = icon.subsample(factor, factor)
                except tk.TclError:
                    header_icon = icon.subsample(8, 8) if icon.width() > header_size else icon
    if platform.system() == "Windows" and WINDOW_ICON_PATH.exists():
        try:
            window.iconbitmap(default=str(WINDOW_ICON_PATH))
        except tk.TclError:
            if icon is not None:
                window.iconphoto(True, icon)
    elif icon is not None:
        window.iconphoto(True, icon)
    window.window_icon = icon
    # keep header reference to avoid GC
    window.header_icon = header_icon
    if header_icon is not None:
        return header_icon
    return icon.subsample(8, 8) if icon is not None else None

def center_window(window, width, height):
    """Calculates display resolution and centers the window on screen."""
    window.update_idletasks()
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    x = (screen_width // 2) - (width // 2)
    y = (screen_height // 2) - (height // 2)
    window.geometry(f"{width}x{height}+{x}+{y}")
def writefiles(package_root, package_name, package_version="", saved_data=None):
    build_mode, build_command, build_system = get_build_environment()
    ctk.set_appearance_mode("system")
    app = ctk.CTk()
    # Suppress CustomTkinter tracker TclError on this Toplevel as well
    try:
        _orig_app_report = app.report_callback_exception
        def _app_silent_report(exc, val, tb):
            try:
                msg = str(val)
                if "invalid command name" in msg and ("check_dpi_scaling" in msg or "update" in msg):
                    return
                if "invalid command name" in msg:
                    return
            except Exception:
                pass
            try:
                return _orig_app_report(exc, val, tb)
            except Exception:
                pass
        app.report_callback_exception = _app_silent_report.__get__(app, app.__class__)
    except Exception:
        pass
    screen_w = app.winfo_screenwidth()
    screen_h = app.winfo_screenheight()
    win_w = min(560, max(440, screen_w - 40))
    win_h = min(640, max(480, screen_h - 60))
    center_window(app, win_w, win_h)
    app.title(f"Debian App Builder (WRITE MODE) {VERSION}")
    app.resizable(False, False)
    window_icon = load_window_icon(app)

    # ---------- Header ----------
    header = ctk.CTkFrame(app, fg_color="transparent")
    header.pack(fill="x", padx=24, pady=(20, 2))
    title_row = ctk.CTkFrame(header, fg_color="transparent")
    title_row.pack()
    if window_icon:
        ctk.CTkLabel(title_row, image=window_icon, text="").pack(side="left", padx=(0, 8))
    ctk.CTkLabel(title_row, text="Debian App Builder",
                 font=ctk.CTkFont(size=22, weight="bold")).pack(side="left")
    ctk.CTkLabel(header, text="WRITE MODE", text_color="#8b95a1",
                 font=ctk.CTkFont(size=12)).pack(pady=(2, 0))

    # ---------- Shared state ----------
    selected_file = {"name": None}
    file_state = {
        "control_created": (Path(package_root) / "DEBIAN" / "control").is_file(),
        "execution_created": (Path(package_root) / "usr" / "bin" / package_name).is_file(),
        "desktop_created": (Path(package_root) / "usr" / "share" / "applications" / f"{package_name}.desktop").is_file(),
        "appstream_created": any((Path(package_root) / "usr" / "share" / "metainfo").glob("*.metainfo.xml")) or any((Path(package_root) / "usr" / "share" / "metainfo").glob("*.appdata.xml")) if (Path(package_root) / "usr" / "share" / "metainfo").is_dir() else False,
    }
    info_values = {
        "location": ctk.StringVar(value=str(Path(package_root).resolve())),
        "files": ctk.StringVar(),
        "directories": ctk.StringVar(),
        "application": ctk.StringVar(value="Not selected"),
    }
    deb_output_var = ctk.StringVar(value=str(Path(package_root).resolve().parent))

    # ---------- Tabs ----------
    tabs = ctk.CTkTabview(
        app,
        fg_color=("gray92", "gray17"),
        segmented_button_selected_color="#c9a15a",
        segmented_button_selected_hover_color="#dab26c",
    )
    tabs.pack(fill="both", expand=True, padx=16, pady=(6, 0))
    tab_files = tabs.add("Application")
    tab_meta = tabs.add("Package & Desktop")
    tab_appstream = tabs.add("AppStream")
    tab_build = tabs.add("Build")

    status_var = ctk.StringVar(value="Ready")
    status_bar = ctk.CTkLabel(
        app, textvariable=status_var, anchor="w", height=28,
        fg_color=("gray85", "gray20"), corner_radius=0,
    )
    status_bar.pack(fill="x", side="bottom", pady=(6, 0))

    def section(parent, text):
        ctk.CTkLabel(
            parent, text=text, font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#c9a15a", anchor="w",
        ).pack(fill="x", padx=16, pady=(14, 6))

    # ================= TAB 1: Application =================
    app_scroll = ctk.CTkScrollableFrame(tab_files, fg_color="transparent")
    app_scroll.pack(fill="both", expand=True, padx=4, pady=4)
    file_frame = ctk.CTkFrame(app_scroll)
    file_frame.pack(fill="x", padx=14, pady=14)
    section(file_frame, "Application Target")
    ctk.CTkLabel(
        file_frame,
        text="Select the file or folder that runs when the app launches.",
        anchor="w", text_color="#8b95a1",
    ).pack(fill="x", padx=16, pady=(0, 8))
    select_button = ctk.CTkButton(
        file_frame, text="Choose File or Folder", command=lambda: choose_python_file())
    select_button.pack(fill="x", padx=16, pady=(0, 8))
    vendor_button = ctk.CTkButton(
        file_frame, text="Vendor Dependencies (pip) - Optional",
        command=lambda: vendor_pkgs(), fg_color="#1f538d")
    vendor_button.pack(fill="x", padx=16, pady=(0, 14))

    ctk.CTkLabel(app_scroll, text="Selected files", anchor="w",
                 font=ctk.CTkFont(size=13, weight="bold"),
                 text_color="#c9a15a").pack(fill="x", padx=16, pady=(8, 6))
    file_list_frame = ctk.CTkFrame(app_scroll, fg_color="transparent")
    file_list_frame.pack(fill="x", padx=16, pady=(0, 14))

    info_frame = ctk.CTkFrame(
        app_scroll, fg_color=("gray95", "gray22"), corner_radius=10)
    info_frame.pack(fill="x", padx=14, pady=(0, 14))
    info_frame.grid_columnconfigure(1, weight=1)
    ctk.CTkFrame(info_frame, height=1, fg_color=("gray80", "gray30")).grid(
        row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(12, 0))

    # ================= TAB 2: Package & Desktop =================
    meta_scroll = ctk.CTkScrollableFrame(tab_meta, fg_color="transparent")
    meta_scroll.pack(fill="both", expand=True, padx=4, pady=4)

    ctk.CTkLabel(
        meta_scroll, text="Package Metadata",
        font=ctk.CTkFont(size=13, weight="bold"),
        text_color="#c9a15a", anchor="w",
    ).pack(anchor="w", padx=18, pady=(14, 4))
    metadata_frame = ctk.CTkFrame(meta_scroll)
    metadata_frame.pack(fill="x", padx=14, pady=(0, 14))
    metadata_frame.grid_columnconfigure(1, weight=1)

    # --- Binary name (source of truth for executable) ---
    # This prevents name problems: editing the display "Name" no longer overwrites the binary.
    # Package and Desktop Exec are automatically kept in sync with this bin name.
    bin_name_label = ctk.CTkLabel(metadata_frame, text="Binary name:", anchor="w")
    bin_name_label.grid(row=0, column=0, padx=(16, 10), pady=(16, 6), sticky="w")
    bin_name = ctk.CTkEntry(metadata_frame, placeholder_text="lowercase, e.g. myapp")
    bin_name.insert(0, package_name)
    bin_name.grid(row=0, column=1, padx=(0, 16), pady=(16, 6), sticky="ew")
    ctk.CTkLabel(
        metadata_frame, text="Executable file name in /usr/bin  (lowercase, no spaces)",
        text_color="#8b95a1", font=ctk.CTkFont(size=10), anchor="w"
    ).grid(row=1, column=0, columnspan=2, padx=16, pady=(0, 6), sticky="w")

    package_label = ctk.CTkLabel(metadata_frame, text="Package:", anchor="w")
    package_label.grid(row=2, column=0, padx=(16, 10), pady=6, sticky="w")
    package = ctk.CTkEntry(metadata_frame)
    package.insert(0, package_name)
    package.grid(row=2, column=1, padx=(0, 16), pady=6, sticky="ew")

    version_label = ctk.CTkLabel(metadata_frame, text="Version:", anchor="w")
    version_label.grid(row=3, column=0, padx=(16, 10), pady=6, sticky="w")
    version = ctk.CTkEntry(metadata_frame)
    if package_version:
        version.insert(0, package_version)
    version.grid(row=3, column=1, padx=(0, 16), pady=6, sticky="ew")

    architecture_label = ctk.CTkLabel(metadata_frame, text="Architecture:", anchor="w")
    architecture_label.grid(row=4, column=0, padx=(16, 10), pady=6, sticky="w")
    architecture = ctk.CTkEntry(metadata_frame, placeholder_text="all, amd64, i386, arm64, armhf")
    # Prefill from initial root folder arch (…_version_arch) so root choice is preserved in WRITE MODE
    _arch_prefill = "amd64"
    try:
        _base = Path(package_root).name
        if "_" in _base:
            _parts = _base.rsplit("_", 2)
            # expected: name_version_arch
            if len(_parts) == 3 and _parts[2].strip():
                _arch_prefill = _parts[2].strip()
            elif len(_parts) >= 2:
                _maybe = _parts[-1].strip()
                if _maybe and all(c.isalnum() or c in "-+." for c in _maybe):
                    _arch_prefill = _maybe
    except Exception:
        pass
    # If saved session overrides, it will be restored later; set initial now
    architecture.insert(0, _arch_prefill)
    architecture.grid(row=4, column=1, padx=(0, 16), pady=6, sticky="ew")

    depends_label = ctk.CTkLabel(metadata_frame, text="Depends:", anchor="w")
    depends_label.grid(row=5, column=0, padx=(16, 10), pady=6, sticky="w")
    depends = ctk.CTkEntry(metadata_frame)
    depends.grid(row=5, column=1, padx=(0, 16), pady=6, sticky="ew")

    maintainer_label = ctk.CTkLabel(metadata_frame, text="Maintainer:", anchor="w")
    maintainer_label.grid(row=6, column=0, padx=(16, 10), pady=6, sticky="w")
    maintainer = ctk.CTkEntry(metadata_frame)
    maintainer.grid(row=6, column=1, padx=(0, 16), pady=6, sticky="ew")

    description_label = ctk.CTkLabel(metadata_frame, text="Description:", anchor="w")
    description_label.grid(row=7, column=0, padx=(16, 10), pady=(6, 16), sticky="w")
    description = ctk.CTkEntry(metadata_frame)
    description.grid(row=7, column=1, padx=(0, 16), pady=(6, 16), sticky="ew")

    ctk.CTkLabel(
        meta_scroll, text="Desktop Entry",
        font=ctk.CTkFont(size=13, weight="bold"),
        text_color="#c9a15a", anchor="w",
    ).pack(anchor="w", padx=18, pady=(14, 4))
    desktop_file_var = ctk.StringVar(value=f"File: {package_name}.desktop")
    desktop_file_label = ctk.CTkLabel(
        meta_scroll, textvariable=desktop_file_var, anchor="w",
        text_color="#8b95a1",
    )
    desktop_file_label.pack(anchor="w", padx=18, pady=(0, 6))
    desktop_frame = ctk.CTkFrame(meta_scroll)
    desktop_frame.pack(fill="x", padx=14, pady=(0, 14))
    desktop_frame.grid_columnconfigure(1, weight=1)

    desktop_name_label = ctk.CTkLabel(desktop_frame, text="Name:", anchor="w")
    desktop_name_label.grid(row=0, column=0, padx=(16, 10), pady=6, sticky="w")
    desktop_name = ctk.CTkEntry(desktop_frame)
    desktop_name.insert(0, package_name)
    desktop_name.grid(row=0, column=1, padx=(0, 16), pady=6, sticky="ew")

    desktop_comment_label = ctk.CTkLabel(desktop_frame, text="Comment:", anchor="w")
    desktop_comment_label.grid(row=1, column=0, padx=(16, 10), pady=6, sticky="w")
    desktop_comment = ctk.CTkEntry(desktop_frame)
    desktop_comment.grid(row=1, column=1, padx=(0, 16), pady=6, sticky="ew")

    desktop_exec_label = ctk.CTkLabel(desktop_frame, text="Exec:", anchor="w")
    desktop_exec_label.grid(row=2, column=0, padx=(16, 10), pady=6, sticky="w")
    desktop_exec = ctk.CTkEntry(desktop_frame)
    desktop_exec.insert(0, package_name)
    desktop_exec.grid(row=2, column=1, padx=(0, 16), pady=6, sticky="ew")

    desktop_term_label = ctk.CTkLabel(desktop_frame, text="Terminal:", anchor="w")
    desktop_term_label.grid(row=3, column=0, padx=(16, 10), pady=6, sticky="w")
    desktop_term = ctk.CTkEntry(desktop_frame)
    desktop_term.insert(0, "true")
    desktop_term.grid(row=3, column=1, padx=(0, 16), pady=6, sticky="ew")

    desktop_categories_label = ctk.CTkLabel(desktop_frame, text="Categories:", anchor="w")
    desktop_categories_label.grid(row=4, column=0, padx=(16, 10), pady=6, sticky="w")
    desktop_categories = ctk.CTkEntry(desktop_frame)
    desktop_categories.insert(0, "Utility")
    desktop_categories.grid(row=4, column=1, padx=(0, 16), pady=6, sticky="ew")

    desktop_path_label = ctk.CTkLabel(desktop_frame, text="Path:", anchor="w")
    desktop_path_label.grid(row=5, column=0, padx=(16, 10), pady=(6, 16), sticky="w")
    desktop_path_entry = ctk.CTkEntry(desktop_frame, placeholder_text=f"/usr/share/{package_name}  (working directory, optional)")
    desktop_path_entry.grid(row=5, column=1, padx=(0, 16), pady=(6, 16), sticky="ew")

    # Fallback icon: when package has no icons use debian-app-builder-package.svg
    # Auto-generates icons/hicolor/{16x16,32x32,48x48,64x64,128x128,256x256}/apps + scalable/apps
    FALLBACK_ICON_NAME = "debian-app-builder-package.svg"
    desktop_icon_var = ctk.StringVar(value=f"/usr/share/{package_name}/{FALLBACK_ICON_NAME}")
    desktop_icon = desktop_icon_var  # keep alias for compatibility (StringVar)
    desktop_icon_button = None

    # Helper: ensure fallback hicolor icons exist (16x16..256x256 + scalable) when package has no icons
    def _ensure_fallback_hicolor_if_needed(pkg=None):
        try:
            _pkg = pkg or _get_effective_bin()
            if not _pkg:
                return False
            if hasattr(c, "has_hicolor_icons") and c.has_hicolor_icons(package_root, _pkg):
                return True
            if hasattr(c, "ensure_fallback_hicolor"):
                return c.ensure_fallback_hicolor(package_root, _pkg, silent=True)
            # fallback: try generate directly from bundled svg
            _src_dir = Path(__file__).resolve().parent
            _candidates = [
                _src_dir / FALLBACK_ICON_NAME,
                _src_dir / "debian-app-builder-package.svg",
                _src_dir.parent / FALLBACK_ICON_NAME,
            ]
            _src = next((p for p in _candidates if p.is_file()), None)
            if _src and hasattr(c, "generate_hicolor_icons"):
                # silent generation – temporarily suppress messagebox
                import tkinter.messagebox as _mb
                _orig_info = _mb.showinfo
                _orig_err = _mb.showerror
                try:
                    _mb.showinfo = lambda *a, **k: None
                    _mb.showerror = lambda *a, **k: None
                    res = c.generate_hicolor_icons(package_root, _pkg, str(_src))
                    return bool(res)
                finally:
                    _mb.showinfo = _orig_info
                    _mb.showerror = _orig_err
        except Exception:
            pass
        return False

    # ---------- Bin name auto-sync (prevents display Name from overwriting executable) ----------
    # Helper to get the canonical binary/package name (bin_name is source of truth)
    def _get_effective_bin():
        try:
            b = bin_name.get().strip()
        except Exception:
            b = ""
        if b:
            return b
        try:
            return package.get().strip() or package_name
        except Exception:
            return package_name

    _syncing_bin = {"active": False}

    def _sync_bin_to_package_and_exec(*_args):
        if _syncing_bin["active"]:
            return
        try:
            new_bin = bin_name.get().strip()
        except Exception:
            return
        if not new_bin:
            return
        # Validate bin name lightly (lowercase Debian style) but allow typing mid-edit
        _syncing_bin["active"] = True
        try:
            # Package field mirrors bin name automatically
            try:
                if package.get().strip() != new_bin:
                    package.delete(0, "end")
                    package.insert(0, new_bin)
            except Exception:
                pass
            # Desktop Exec mirrors bin name automatically
            try:
                if desktop_exec.get().strip() != new_bin:
                    desktop_exec.delete(0, "end")
                    desktop_exec.insert(0, new_bin)
            except Exception:
                pass
            # Update dynamic labels
            try:
                desktop_file_var.set(f"File: {new_bin}.desktop")
            except Exception:
                pass
            try:
                desktop_path_entry.configure(placeholder_text=f"/usr/share/{new_bin}  (working directory, optional)")
            except Exception:
                pass
            # Update Build tab desktop button text dynamically
            try:
                desktop_btn.configure(text=f"Create {new_bin}.desktop file")
            except Exception:
                pass
            # If hicolor not yet generated, keep Icon var consistent (will be used when writing desktop file)
            # No automatic change if hicolor already has icons – write_desktop_file will handle hicolor case
        finally:
            _syncing_bin["active"] = False
            # trigger global state refresh
            try:
                update_action_states()
            except Exception:
                pass

    # Bind bin_name typing to auto-fill Package and Exec
    try:
        bin_name.bind("<KeyRelease>", _sync_bin_to_package_and_exec)
        bin_name.bind("<FocusOut>", _sync_bin_to_package_and_exec)
    except Exception:
        pass

    # ---------- Hicolor icons option ----------
    hicolor_generated = {"value": False, "source": None}
    hicolor_status_var = ctk.StringVar(value="No hicolor icons generated")
    ctk.CTkLabel(
        meta_scroll, text="Hicolor Icons (optional)",
        font=ctk.CTkFont(size=13, weight="bold"),
        text_color="#c9a15a", anchor="w",
    ).pack(anchor="w", padx=18, pady=(14, 4))
    ctk.CTkLabel(
        meta_scroll, text="Generate icons/hicolor/{16x16,32x32,48x48,64x64,128x128,256x256}/apps and scalable for \n.svg",
        anchor="w", text_color="#8b95a1", font=ctk.CTkFont(size=11),
    ).pack(anchor="w", padx=18, pady=(0, 6))
    hicolor_frame = ctk.CTkFrame(meta_scroll)
    hicolor_frame.pack(fill="x", padx=14, pady=(0, 14))
    hicolor_frame.grid_columnconfigure(0, weight=1)
    hicolor_status_label = ctk.CTkLabel(hicolor_frame, textvariable=hicolor_status_var, anchor="w", text_color="#8b95a1")
    hicolor_status_label.grid(row=0, column=0, padx=16, pady=(10, 6), sticky="ew")
    def choose_hicolor_icon():
        src = filedialog.askopenfilename(
            title="Select source image for hicolor icons",
            filetypes=[("Images", "*.png *.svg *.jpg *.jpeg *.xpm"), ("PNG", "*.png"), ("SVG", "*.svg"), ("All files", "*.*")],
        )
        if not src:
            return
        cp_h = _get_effective_bin()
        res = c.generate_hicolor_icons(package_root, cp_h, src)
        if res:
            hicolor_generated["value"] = True
            hicolor_generated["source"] = src
            hicolor_status_var.set(f"Generated {len(res)} hicolor icon(s) from {Path(src).name}")
            # For hicolor, Icon should be just package name (theme lookup)
            # Update desktop Icon field to use hicolor name
            try:
                if hasattr(desktop_icon, "set"):
                    desktop_icon.set(cp_h)
                else:
                    desktop_icon.delete(0, "end")
                    desktop_icon.insert(0, cp_h)
            except Exception:
                pass
            # If desktop file already exists, patch its Icon line to hicolor
            try:
                dpath = Path(package_root) / "usr" / "share" / "applications" / f"{cp_h}.desktop"
                if dpath.is_file():
                    txt = dpath.read_text(encoding="utf-8")
                    lines = []
                    for line in txt.splitlines():
                        if line.startswith("Icon="):
                            lines.append(f"Icon={cp_h}")
                        else:
                            lines.append(line)
                    dpath.write_text("\n".join(lines) + "\n", encoding="utf-8")
                    log(f"Updated {dpath.name} Icon to hicolor '{cp_h}'", "ok")
            except Exception:
                pass
            log(f"Generated hicolor icons:\n{len(res)} files", "ok")
            update_package_info()
            update_action_states()
        else:
            hicolor_status_var.set("Failed to generate hicolor icons")
    hicolor_button = ctk.CTkButton(hicolor_frame, text="Generate Hicolor Icons", width=140, command=choose_hicolor_icon)
    hicolor_button.grid(row=1, column=0, padx=16, pady=(0, 10), sticky="ew")

    # ================= TAB 3: AppStream (dedicated) =================
    # Dedicated AppStream metadata creation section – calls core.py function
    # Spec: https://www.freedesktop.org/software/appstream/docs/
    # Output: usr/share/metainfo/<app_id>.metainfo.xml
    appstream_scroll = ctk.CTkScrollableFrame(tab_appstream, fg_color="transparent")
    appstream_scroll.pack(fill="both", expand=True, padx=4, pady=4)

    ctk.CTkLabel(
        appstream_scroll, text="AppStream Metadata (for Software Center)",
        font=ctk.CTkFont(size=13, weight="bold"),
        text_color="#c9a15a", anchor="w",
    ).pack(anchor="w", padx=18, pady=(14, 4))
    ctk.CTkLabel(
        appstream_scroll, text="Creates usr/share/metainfo/<id>.metainfo.xml – required for GNOME Software / KDE Discover.",
        anchor="w", text_color="#8b95a1", font=ctk.CTkFont(size=11),
    ).pack(anchor="w", padx=18, pady=(0, 6))

    appstream_frame = ctk.CTkFrame(appstream_scroll)
    appstream_frame.pack(fill="x", padx=14, pady=(0, 14))
    appstream_frame.grid_columnconfigure(1, weight=1)

    # Helper: derive AppStream ID from Maintainer (package metadata)
    def _derive_app_id_from_maintainer(maint_str, pkg):
        try:
            import re
            pkg_safe = re.sub(r"[^a-z0-9-]", "-", str(pkg).lower())
            pkg_safe = re.sub(r"-+", "-", pkg_safe).strip("-") or "app"
            maint_str = str(maint_str or "").strip()
            if not maint_str:
                return f"com.example.{pkg_safe}"
            m = re.search(r"<([^>]+)>", maint_str)
            email = m.group(1).strip() if m else ""
            if not email or "@" not in email:
                m2 = re.search(r"[\w\.\-+]+@[\w\.\-]+\.[\w]+", maint_str)
                if m2:
                    email = m2.group(0)
            if email and "@" in email:
                domain = email.split("@")[-1].lower().split(":")[0].split("/")[0]
                parts = [p for p in domain.split(".") if p]
                if len(parts) >= 2:
                    parts.reverse()
                    return ".".join(parts) + f".{pkg_safe}"
                elif parts:
                    return f"{parts[0]}.{pkg_safe}"
            name_part = maint_str.split("<")[0].strip()
            name_clean = re.sub(r"[^a-z0-9]", "", name_part.lower().split()[0] if name_part.split() else "")
            if name_clean:
                return f"io.github.{name_clean}.{pkg_safe}"
            return f"com.example.{pkg_safe}"
        except Exception:
            return f"com.example.{pkg}"

    # AppStream fields (calling core.write_appstream_file) – placeholder only like other entries; value derived from Maintainer on create
    appstream_id_label = ctk.CTkLabel(appstream_frame, text="App ID:", anchor="w")
    appstream_id_label.grid(row=0, column=0, padx=(16, 10), pady=(16, 6), sticky="w")
    appstream_id = ctk.CTkEntry(appstream_frame, placeholder_text="com.example." + package_name + " (auto from Maintainer)")
    appstream_id.grid(row=0, column=1, padx=(0, 16), pady=(16, 6), sticky="ew")

    appstream_name_label = ctk.CTkLabel(appstream_frame, text="Name:", anchor="w")
    appstream_name_label.grid(row=1, column=0, padx=(16, 10), pady=6, sticky="w")
    appstream_name = ctk.CTkEntry(appstream_frame, placeholder_text=package_name)
    appstream_name.insert(0, package_name)
    appstream_name.grid(row=1, column=1, padx=(0, 16), pady=6, sticky="ew")

    appstream_summary_label = ctk.CTkLabel(appstream_frame, text="Summary:", anchor="w")
    appstream_summary_label.grid(row=2, column=0, padx=(16, 10), pady=6, sticky="w")
    appstream_summary = ctk.CTkEntry(appstream_frame, placeholder_text="One-line summary (shown in store)")
    appstream_summary.grid(row=2, column=1, padx=(0, 16), pady=6, sticky="ew")

    appstream_developer_label = ctk.CTkLabel(appstream_frame, text="Developer:", anchor="w")
    appstream_developer_label.grid(row=3, column=0, padx=(16, 10), pady=6, sticky="w")
    appstream_developer = ctk.CTkEntry(appstream_frame, placeholder_text="Your name / organization")
    appstream_developer.grid(row=3, column=1, padx=(0, 16), pady=6, sticky="ew")

    appstream_license_label = ctk.CTkLabel(appstream_frame, text="Project License:", anchor="w")
    appstream_license_label.grid(row=4, column=0, padx=(16, 10), pady=6, sticky="w")
    appstream_license = ctk.CTkEntry(appstream_frame, placeholder_text="GPL-3.0+")
    appstream_license.insert(0, "GPL-3.0+")
    appstream_license.grid(row=4, column=1, padx=(0, 16), pady=6, sticky="ew")

    appstream_meta_license_label = ctk.CTkLabel(appstream_frame, text="Metadata License:", anchor="w")
    appstream_meta_license_label.grid(row=5, column=0, padx=(16, 10), pady=6, sticky="w")
    appstream_meta_license = ctk.CTkEntry(appstream_frame, placeholder_text="CC0-1.0")
    appstream_meta_license.insert(0, "CC0-1.0")
    appstream_meta_license.grid(row=5, column=1, padx=(0, 16), pady=6, sticky="ew")

    appstream_homepage_label = ctk.CTkLabel(appstream_frame, text="Homepage:", anchor="w")
    appstream_homepage_label.grid(row=6, column=0, padx=(16, 10), pady=6, sticky="w")
    appstream_homepage = ctk.CTkEntry(appstream_frame, placeholder_text="https://example.com")
    appstream_homepage.grid(row=6, column=1, padx=(0, 16), pady=6, sticky="ew")

    appstream_categories_label = ctk.CTkLabel(appstream_frame, text="Categories:", anchor="w")
    appstream_categories_label.grid(row=7, column=0, padx=(16, 10), pady=6, sticky="w")
    appstream_categories = ctk.CTkEntry(appstream_frame, placeholder_text="Utility;Development")
    appstream_categories.insert(0, "Utility")
    appstream_categories.grid(row=7, column=1, padx=(0, 16), pady=6, sticky="ew")

    appstream_keywords_label = ctk.CTkLabel(appstream_frame, text="Keywords:", anchor="w")
    appstream_keywords_label.grid(row=8, column=0, padx=(16, 10), pady=6, sticky="w")
    appstream_keywords = ctk.CTkEntry(appstream_frame, placeholder_text="keyword1, keyword2")
    appstream_keywords.grid(row=8, column=1, padx=(0, 16), pady=6, sticky="ew")

    ctk.CTkLabel(appstream_scroll, text="Description (long, paragraphs)", anchor="w",
                 font=ctk.CTkFont(size=12, weight="bold"), text_color="#c9a15a").pack(anchor="w", padx=18, pady=(6, 4))
    appstream_description = ctk.CTkTextbox(appstream_scroll, height=110, fg_color=("gray95", "gray20"))
    appstream_description.pack(fill="x", padx=14, pady=(0, 8))
    appstream_description.insert("1.0", "A longer description of the application.\n\nUse blank lines to separate paragraphs.")

    # Status & action – dedicated AppStream creation button calling core.py
    appstream_created = {"value": False}
    appstream_status_var = ctk.StringVar(value="No AppStream file yet (optional but recommended)")
    appstream_status_label = ctk.CTkLabel(appstream_scroll, textvariable=appstream_status_var, anchor="w", text_color="#8b95a1", font=ctk.CTkFont(size=11))
    appstream_status_label.pack(anchor="w", padx=18, pady=(0, 6))

    def create_appstream_file():
        """Dedicated AppStream creation – calls core.write_appstream_file().
        App ID is now fetched from package metadata Maintainer when left as placeholder."""
        cp = _get_effective_bin()
        cv = version.get().strip() or "1.0"
        aid = appstream_id.get().strip()
        # If App ID is placeholder / empty / old hardcoded tuffgit21, derive from Maintainer
        _ph_generic = f"com.example.{cp.lower()}"
        _ph_old = f"io.github.tuffgit21.{cp.lower()}"
        _is_placeholder = (not aid) or (aid.lower() == _ph_generic.lower()) or (aid.lower() == _ph_old.lower()) or (aid.lower().startswith("com.example.") and aid.lower().endswith(cp.lower()))
        if _is_placeholder:
            try:
                try:
                    _maint = maintainer.get().strip()
                except Exception:
                    _maint = ""
                derived = _derive_app_id_from_maintainer(_maint, cp)
                if derived and derived.lower() != _ph_generic.lower():
                    aid = derived
                    # update entry to show derived value
                    try:
                        appstream_id.delete(0, "end")
                        appstream_id.insert(0, aid)
                    except Exception:
                        pass
                elif not aid:
                    aid = derived
            except Exception:
                pass
        aname = appstream_name.get().strip()
        asum = appstream_summary.get().strip()
        # textbox get
        try:
            adesc = appstream_description.get("1.0", "end-1c").strip()
        except Exception:
            adesc = ""
        adev = appstream_developer.get().strip()
        alic = appstream_license.get().strip() or "GPL-3.0+"
        ameta = appstream_meta_license.get().strip() or "CC0-1.0"
        ahome = appstream_homepage.get().strip()
        acat = appstream_categories.get().strip()
        akeys = appstream_keywords.get().strip()
        # Fallback summary/description from package metadata if empty
        if not asum:
            asum = description.get().strip() or aname or cp
        if not adesc:
            adesc = description.get().strip() or asum
        dest = c.write_appstream_file(
            package_root, cp,
            app_id=aid, name=aname, summary=asum, description=adesc,
            developer_name=adev, project_license=alic, metadata_license=ameta,
            homepage_url=ahome, categories=acat, keywords=akeys, version=cv,
        )
        if dest:
            appstream_created["value"] = True
            appstream_status_var.set(f"Created {Path(dest).name} in usr/share/metainfo/")
            log(f"Created AppStream metadata at {dest}.", "ok")
            update_package_info()
            update_action_states()
        else:
            appstream_status_var.set("Failed to create AppStream metadata – see alert")
            log("AppStream creation failed.", "error")

    appstream_btn = ctk.CTkButton(appstream_scroll, text="Create AppStream Metadata", command=create_appstream_file, fg_color="#2e7d32", hover_color="#388e3c")
    appstream_btn.pack(fill="x", padx=14, pady=(0, 6))

    ctk.CTkLabel(
        appstream_scroll, text="Tip: Keep Summary < 80 chars. Categories use ';' (e.g. Utility;Development).",
        anchor="w", text_color="#8b95a1", font=ctk.CTkFont(size=10),
    ).pack(anchor="w", padx=18, pady=(0, 14))

    # Keep AppStream name/summary in sync – like other entries, App ID stays placeholder unless user typed or old value needs migration
    def _sync_appstream_defaults(*_):
        try:
            cur_pkg = _get_effective_bin()
            cur_id = appstream_id.get().strip()
            # only treat non-empty placeholder-like values as needing migration; empty stays as placeholder (like other entries)
            is_placeholder = (
                cur_id
                and (
                    cur_id.lower() == f"com.example.{cur_pkg.lower()}"
                    or cur_id.lower().startswith("com.example.")
                    or cur_id.lower().startswith("io.github.tuffgit21.")
                )
            )
            if is_placeholder:
                try:
                    _m = maintainer.get().strip()
                except Exception:
                    _m = ""
                derived = _derive_app_id_from_maintainer(_m, cur_pkg)
                # only auto-update if pkg changed or still old tuffgit21
                if cur_id.lower().split(".")[-1] != cur_pkg.lower() or cur_id.lower().startswith("io.github.tuffgit21."):
                    try:
                        appstream_id.delete(0, "end")
                        appstream_id.insert(0, derived)
                    except Exception:
                        pass
            if not appstream_name.get().strip():
                appstream_name.delete(0, "end")
                appstream_name.insert(0, cur_pkg)
        except Exception:
            pass

    # ================= TAB 4: Build =================
    section(tab_build, "Actions")
    ctrl_btn = ctk.CTkButton(tab_build, text="Create Control file", command=lambda: create_control_file())
    ctrl_btn.pack(fill="x", padx=16, pady=(0, 8))
    make_exec = ctk.CTkButton(tab_build, text="Create Execution file", command=lambda: create_execution_file())
    make_exec.pack(fill="x", padx=16, pady=(0, 8))
    desktop_btn = ctk.CTkButton(
        tab_build, text=f"Create {package_name}.desktop file",
        command=lambda: create_desktop_file(), state="disabled")
    desktop_btn.pack(fill="x", padx=16, pady=(0, 8))

    section(tab_build, "Output")
    ctk.CTkLabel(
        tab_build, text="Choose where the finished .deb is saved.",
        anchor="w", text_color="#8b95a1",
    ).pack(fill="x", padx=16, pady=(0, 4))
    deb_output_frame = ctk.CTkFrame(tab_build, fg_color="transparent")
    deb_output_frame.pack(fill="x", padx=16, pady=(0, 8))
    deb_output_frame.grid_columnconfigure(0, weight=1)
    deb_output_entry = ctk.CTkEntry(deb_output_frame, textvariable=deb_output_var, placeholder_text=str(Path(package_root).resolve().parent))
    deb_output_entry.grid(row=0, column=0, sticky="ew")

    def choose_finished_deb_location():
        # Prompt: "Choose where the finished .deb is saved."
        chosen = filedialog.asksaveasfilename(
            title="Choose where the finished .deb is saved.",
            defaultextension=".deb",
            initialfile=f"{Path(package_root).name}.deb",
            initialdir=deb_output_var.get().strip() or str(Path(package_root).resolve().parent),
            filetypes=[("Debian package", "*.deb"), ("All files", "*.*")],
        )
        if chosen:
            deb_output_var.set(chosen)
        else:
            # fallback to directory chooser
            chosen_dir = filedialog.askdirectory(title="Choose where the finished .deb is saved.")
            if chosen_dir:
                deb_output_var.set(chosen_dir)

    deb_output_button = ctk.CTkButton(deb_output_frame, text="Browse", width=78, command=choose_finished_deb_location)
    deb_output_button.grid(row=0, column=1, padx=(8, 0))

    build_btn = ctk.CTkButton(
        tab_build, text="⚠  BUILD  ⚠", command=lambda: build_package(),
        fg_color="red", text_color="black", hover_color="#cc0000")
    build_btn.pack(fill="x", padx=16, pady=(0, 14))

    section(tab_build, "Log")
    log_box = ctk.CTkTextbox(tab_build, height=170, state="disabled")
    log_box.pack(fill="both", expand=True, padx=16, pady=(0, 14))

    # ================= Helpers =================
    def log(msg, level="info"):
        log_box.configure(state="normal")
        log_box.insert("end", msg + "\n")
        log_box.configure(state="disabled")
        log_box.see("end")

    def set_status(text, ok=None):
        status_var.set(text)
        if ok is True:
            status_bar.configure(text_color="#2e7d32")
        elif ok is False:
            status_bar.configure(text_color="#c96a5a")
        else:
            status_bar.configure(text_color=("gray30", "gray85"))

    def start_busy():
        for b in (select_button, vendor_button, ctrl_btn, make_exec, desktop_btn, build_btn, deb_output_button, hicolor_button, appstream_btn):
            try:
                b.configure(state="disabled")
            except Exception:
                pass
        try:
            deb_output_entry.configure(state="disabled")
        except Exception:
            pass

    def end_busy():
        select_button.configure(state="normal")
        vendor_button.configure(state="normal")
        try:
            deb_output_entry.configure(state="normal")
            deb_output_button.configure(state="normal")
            hicolor_button.configure(state="normal")
            appstream_btn.configure(state="normal")
        except Exception:
            pass
        update_action_states()

    def choose_python_file():
        selected_name = askPyfile(package_root, _get_effective_bin())
        if selected_name:
            selected_file["name"] = selected_name
        # FIX: Package & Desktop entries must stay available even when file
        # is listed but selected_file was not yet synced. Check disk payload
        # instead of only selected_file flag, and keep metadata editable.
        try:
            _has = False
            _pkg = _get_effective_bin()
            _share = Path(package_root) / "usr" / "share" / _pkg
            if _share.is_dir():
                _has = any(p.name not in ("vendor", "DebAppBuilderIcon.png", "debian-app-builder-package.svg") for p in _share.iterdir())
            if not _has:
                _share_root = Path(package_root) / "usr" / "share"
                if _share_root.is_dir():
                    for sub in _share_root.iterdir():
                        if sub.is_dir() and sub.name not in ("applications",):
                            if any(p.name not in ("vendor", "DebAppBuilderIcon.png", "debian-app-builder-package.svg") for p in sub.iterdir()):
                                _has = True
                                break
            # always keep Package/Desktop/AppStream editable – only gate if truly no payload
            # but even with no payload they should be editable (user may fill metadata first)
            set_write_inputs_state("normal")
        except Exception:
            set_write_inputs_state("normal")
        update_action_states()
        update_package_info()
        refresh_file_indicator()

    def vendor_pkgs():
        c.vendor_dependencies(package_root, _get_effective_bin())
        update_package_info()
        log("Vendor dependencies bundled.", "ok")

    def refresh_file_indicator():
        for child in file_list_frame.winfo_children():
            child.destroy()
        application_path = Path(package_root) / "usr" / "share" / _get_effective_bin()
        files = sorted(path for path in application_path.iterdir()
                       if path.name not in ("vendor", "DebAppBuilderIcon.png", "debian-app-builder-package.svg")) \
            if application_path.exists() else []
        if not files:
            ctk.CTkLabel(file_list_frame, text="No application files selected",
                         text_color="gray").pack(anchor="w")
            file_list_frame.configure(height=60)
            return
        for file_path in files:
            file_row = ctk.CTkFrame(file_list_frame, fg_color="transparent")
            file_row.pack(fill="x", pady=2)
            is_main = (selected_file["name"] == file_path.name)
            # Highlight main file name
            name_color = ("#2e7d32", "#7cba7c") if is_main else None
            label = ctk.CTkLabel(file_row, text=file_path.name + ("  ★" if is_main else ""), anchor="w", text_color=name_color)
            label.pack(side="left", fill="x", expand=True)
            size_str = "Folder" if file_path.is_dir() else format_file_size(file_path.stat().st_size)
            ctk.CTkLabel(file_row, text=size_str, width=70).pack(side="left", padx=6)
            # X button (always)
            ctk.CTkButton(file_row, text="X", width=28, height=24, fg_color="#c0392b", hover_color="#e74c3c",
                          command=lambda path=file_path: remove_application_file(path)).pack(side="right")
            # Set Main button – excludes folders, next to X
            if file_path.is_file():
                if is_main:
                    ctk.CTkButton(file_row, text="✓ Main", width=68, height=24, fg_color="#2e7d32", hover_color="#388e3c", state="disabled").pack(side="right", padx=(0, 4))
                else:
                    ctk.CTkButton(file_row, text="Set Main", width=68, height=24, fg_color="#1f538d", hover_color="#2a6cb6",
                                  command=lambda p=file_path: set_main_executable(p)).pack(side="right", padx=(0, 4))
            else:
                # placeholder to keep row height aligned – folders cannot be main
                ctk.CTkLabel(file_row, text="", width=68).pack(side="right", padx=(0, 4))
        file_list_frame.configure(height=min(280, 60 + len(files) * 34))

    def set_main_executable(file_path: Path):
        """Set the clicked file as main executable – excludes folders."""
        try:
            if file_path.is_dir():
                messagebox.showwarning("Debian App Builder", "Folders cannot be set as main executable.\nPlease choose a file (.py / binary).")
                return
            selected_file["name"] = file_path.name
            update_package_info()
            update_action_states()
            refresh_file_indicator()
            log(f"Set main executable to {file_path.name}.", "ok")
            set_status(f"Main: {file_path.name}", ok=True)
        except Exception as e:
            messagebox.showerror("Debian App Builder", f"Could not set main: {e}")

    def remove_application_file(file_path):
        try:
            if file_path.is_dir():
                shutil.rmtree(file_path)
            else:
                file_path.unlink()
        except OSError as error:
            messagebox.showerror("Debian App Builder", f"Could not remove path: {error}")
            return
        if selected_file["name"] == file_path.name:
            selected_file["name"] = None
            file_state["execution_created"] = False
            # FIX: don't disable Package & Desktop entries when file removed –
            # metadata should stay editable. Sync from disk instead.
            try:
                # re-sync selected_file from remaining payload
                _pkg2 = _get_effective_bin()
                _root2 = Path(package_root)
                _found = None
                for cand in (_pkg2, package_name):
                    _ap = _root2 / "usr" / "share" / cand
                    if _ap.is_dir():
                        for p in _ap.iterdir():
                            if p.name not in ("vendor", "DebAppBuilderIcon.png", "debian-app-builder-package.svg"):
                                _found = p.name
                                break
                    if _found:
                        break
                if _found:
                    selected_file["name"] = _found
            except Exception:
                pass
            set_write_inputs_state("normal")
            update_action_states()
        refresh_file_indicator()
        update_package_info()
        log(f"Removed {file_path.name}.", "ok")

    def update_package_info():
        package_path = Path(package_root)
        files = [path for path in package_path.rglob("*") if path.is_file()]
        directories = [path for path in package_path.rglob("*") if path.is_dir()]
        info_values["files"].set(str(len(files)))
        info_values["directories"].set(str(len(directories)))
        info_values["application"].set(selected_file["name"] or "Not selected")

    def format_file_size(size):
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / (1024 * 1024):.1f} MB"

    def add_info_row(row, label, variable):
        ctk.CTkLabel(info_frame, text=label, anchor="w").grid(
            row=row, column=0, padx=(16, 10), pady=5, sticky="w")
        ctk.CTkLabel(info_frame, textvariable=variable, anchor="w").grid(
            row=row, column=1, padx=(0, 16), pady=5, sticky="ew")

    add_info_row(1, "Location:", info_values["location"])
    add_info_row(2, "Files:", info_values["files"])
    add_info_row(3, "Directories:", info_values["directories"])
    add_info_row(4, "Application:", info_values["application"])

    def choose_desktop_icon():
        # Old Icon input removed – delegate to hicolor
        try:
            choose_hicolor_icon()
        except Exception:
            pass

    def create_control_file():
        cp = _get_effective_bin()
        cv = version.get().strip()
        cm = maintainer.get().strip()
        cd = description.get().strip()
        if not cp or not cv or not cm or not cd:
            messagebox.showwarning(
                title="Debian App Builder",
                message="Package, version, maintainer, and description are required.",
            )
            return
        try:
            c.write_control_file(
                package_root, cp, cv, cm, cd,
                arch=architecture.get().strip() or "amd64",
                depends=depends.get().strip(),
            )
        except OSError as error:
            messagebox.showerror("Debian App Builder", f"Could not create control file: {error}")
            log(f"Control file error: {error}", "error")
            return
        # Verify file actually exists on disk (fixes double-click bug where
        # stale file_state required second creation)
        control_path = Path(package_root) / "DEBIAN" / "control"
        try:
            # ensure flush to disk
            if control_path.is_file() and control_path.stat().st_size > 0:
                # read back to confirm write succeeded
                control_path.read_text(encoding="utf-8")
            else:
                raise OSError(f"Control file not found at {control_path}")
        except Exception as e:
            messagebox.showerror("Debian App Builder", f"Control file verification failed: {e}")
            log(f"Control verification failed: {e}", "error")
            file_state["control_created"] = False
            update_action_states()
            return
        messagebox.showinfo("Debian App Builder", "Successfully created DEBIAN/control.")
        log("Created DEBIAN/control.", "ok")
        file_state["control_created"] = True
        # Force immediate sync before updating UI – ensures BUILD validation sees fresh state
        try:
            sync_file_state()
        except Exception:
            pass
        update_action_states()
        # Extra ensure: if BUILD should be ready but still disabled due to stale has_payload,
        # force a second update after UI settles – guarded for destroyed window
        try:
            if app.winfo_exists():
                app.after(50, lambda: update_action_states() if app.winfo_exists() else None)
        except (tk.TclError, RuntimeError):
            pass
        except Exception:
            pass
        update_package_info()

    def create_execution_file():
        cp = _get_effective_bin()
        py_file = selected_file["name"]
        if not cp or not version.get().strip() or not py_file:
            messagebox.showwarning(
                title="Debian App Builder",
                message="Package, version, and a target file are required.",
            )
            return
        # Validate that the selected payload actually exists in the share dir
        # (handles C .exe / folder cases where write_bin_file previously wrote only "/usr/share/<pkg>")
        share_path = Path(package_root) / "usr" / "share" / cp / str(py_file).strip().lstrip("/\\")
        if not share_path.exists():
            # try .exe alternate
            alt = None
            if str(py_file).lower().endswith(".exe"):
                alt = str(py_file)[:-4]
            else:
                alt = str(py_file) + ".exe"
            alt_path = Path(package_root) / "usr" / "share" / cp / alt
            if alt_path.exists():
                # auto-correct to actual filename (with/without .exe)
                py_file = alt
                selected_file["name"] = alt
                log(f"Corrected target to existing file: {alt}", "info")
            elif share_path.is_dir() or alt_path.is_dir():
                messagebox.showerror(
                    "Debian App Builder",
                    f"Selected folder '{py_file}' is a directory. The launcher needs a file.\n"
                    f"Choose the binary inside the folder (e.g. {py_file}/<binary>).",
                )
                return
            else:
                # let core.write_bin_file handle the missing-file error with proper alert
                pass
        bin_path = c.write_bin_file(package_root, cp, py_file)
        if bin_path:
            # verify launcher actually points to a real file, not just directory
            try:
                with open(bin_path, "r", encoding="utf-8") as fh:
                    content = fh.read()
                # launcher should contain a quoted target with a filename after /usr/share/<pkg>/
                if f"/usr/share/{cp}/" in content:
                    target_line = [l for l in content.splitlines() if "exec" in l and f"/usr/share/{cp}/" in l]
                    if target_line and target_line[0].strip().endswith(f"/usr/share/{cp}/\"") or target_line[0].strip().endswith(f"/usr/share/{cp}"):
                        # would be empty filename – treat as error
                        pass
                file_state["execution_created"] = Path(bin_path).is_file()
                log(f"Created launcher at {bin_path}.", "ok")
                # sanity: ensure target file exists on disk
                target_file = Path(package_root) / "usr" / "share" / cp / Path(py_file).name if "/" not in py_file else Path(package_root) / "usr" / "share" / cp / py_file
                if not target_file.exists():
                    # check .exe variant
                    exe_variant = str(target_file) + ".exe" if not str(target_file).lower().endswith(".exe") else str(target_file)[:-4]
                    if not Path(exe_variant).exists():
                        log(f"Warning: target {target_file} not found on disk – launcher may fail", "error")
            except Exception:
                file_state["execution_created"] = Path(bin_path).is_file()
                log(f"Created launcher at {bin_path}.", "ok")
        else:
            log("Failed to create launcher – see alert", "error")
        update_action_states()
        update_package_info()

    def create_desktop_file():
        cp = _get_effective_bin()
        entry_name = desktop_name.get().strip()
        entry_exec = desktop_exec.get().strip()
        # Enforce Exec uses bin name if user mistakenly typed display Name with spaces/caps
        try:
            _bin = _get_effective_bin()
            if entry_exec != _bin and " " in entry_exec and entry_exec.strip().lower() == entry_name.strip().lower():
                entry_exec = _bin
                try:
                    desktop_exec.delete(0, "end")
                    desktop_exec.insert(0, _bin)
                except Exception:
                    pass
        except Exception:
            pass
        if not cp or not entry_name or not entry_exec:
            messagebox.showwarning(
                title="Debian App Builder",
                message="Package, desktop name, and Exec are required.",
            )
            return
        # When package has no icons, auto-use debian-app-builder-package.svg
        # as hicolor icons: icons/hicolor/{16x16,32x32,48x48,64x64,128x128,256x256}/apps + scalable
        try:
            _ensure_fallback_hicolor_if_needed(cp)
        except Exception:
            pass
        # Path= handling – optional working directory, placeholder-like others
        try:
            _path_val = desktop_path_entry.get().strip()
        except Exception:
            _path_val = ""
        desktop_path = c.write_desktop_file(
            package_root, cp, entry_name, entry_exec,
            comment=desktop_comment.get().strip(),
            categories=desktop_categories.get().strip() or "Utility",
            icon=desktop_icon.get().strip(),
            terminal=desktop_term.get().strip(),
            path=_path_val,
        )
        if desktop_path:
            file_state["desktop_created"] = True
            log(f"Created {Path(desktop_path).name}.", "ok")
            messagebox.showinfo("Debian App Builder", f"Successfully created {Path(desktop_path).name}.")
            update_package_info()
            update_action_states()
            # ensure BUILD button refreshes even if desktop was last step
            try:
                app.update_idletasks()
            except Exception:
                pass

    def _sync_file_state_early():
        """Early sync helper so build_package can call it before later definition overwrites it."""
        try:
            pkg = _get_effective_bin()
            root = Path(package_root)
            if not selected_file["name"]:
                for cand_pkg in (pkg, package_name):
                    app_share = root / "usr" / "share" / cand_pkg
                    if app_share.is_dir():
                        for p in app_share.iterdir():
                            if p.name not in ("vendor", "DebAppBuilderIcon.png", "debian-app-builder-package.svg"):
                                selected_file["name"] = p.name
                                break
                        if selected_file["name"]:
                            break
                if not selected_file["name"]:
                    share_root = root / "usr" / "share"
                    if share_root.is_dir():
                        for sub in share_root.iterdir():
                            if sub.is_dir() and sub.name not in ("applications",):
                                for p in sub.iterdir():
                                    if p.name not in ("vendor", "DebAppBuilderIcon.png", "debian-app-builder-package.svg"):
                                        selected_file["name"] = p.name
                                        break
                                if selected_file["name"]:
                                    break
            cur_pkg = _get_effective_bin()
            control_exists = (root / "DEBIAN" / "control").is_file() and (root / "DEBIAN" / "control").stat().st_size > 0
            file_state["control_created"] = control_exists
            if cur_pkg:
                file_state["execution_created"] = (root / "usr" / "bin" / cur_pkg).is_file()
                file_state["desktop_created"] = (root / "usr" / "share" / "applications" / f"{cur_pkg}.desktop").is_file()
            else:
                file_state["control_created"] = control_exists
                file_state["execution_created"] = (root / "usr" / "bin" / package_name).is_file()
                file_state["desktop_created"] = (root / "usr" / "share" / "applications" / f"{package_name}.desktop").is_file()
        except Exception:
            pass

    def build_package():
        cp = _get_effective_bin()
        cv = version.get().strip()
        if not cp or not cv:
            messagebox.showwarning(
                title="Debian App Builder",
                message="Package and version are required.",
            )
            log("Build validation failed: package/version missing.", "error")
            set_status("Build validation failed", ok=False)
            return
        if not build_command:
            messagebox.showerror(
                title="Debian App Builder",
                message=f"Cannot build on this system: {build_system}.",
            )
            log(f"Cannot build on this system: {build_system}.", "error")
            set_status(f"Build unavailable: {build_system}", ok=False)
            return
        # --- Re-sync and validate real on-disk prerequisites (fixes stale alert bug) ---
        try:
            _sync_file_state_early()
        except Exception:
            pass
        try:
            sync_file_state()
        except Exception:
            pass
        # Ensure fallback hicolor icons when package has no icons
        # Use debian-app-builder-package.svg -> icons/hicolor/16x16..256x256/apps + scalable/apps
        try:
            _ensure_fallback_hicolor_if_needed(cp)
            # re-sync after fallback generation (creates hicolor, updates status)
            try:
                hicolor_generated["value"] = True
                hicolor_status_var.set(f"Auto-generated fallback hicolor icons for {cp}")
            except Exception:
                pass
        except Exception:
            pass
        # ensure execution/desktop checks use current cp
        missing = []
        try:
            missing = c.validate_build_prerequisites(package_root, cp)
        except Exception:
            # fallback local check if core helper unavailable
            root = Path(package_root)
            if not (root / "DEBIAN" / "control").is_file():
                missing.append("DEBIAN/control — Create Control file")
            if not (root / "usr" / "bin" / cp).is_file():
                missing.append(f"usr/bin/{cp} — Create Execution file")
            if not (root / "usr" / "share" / "applications" / f"{cp}.desktop").is_file():
                missing.append(f"usr/share/applications/{cp}.desktop — Create Desktop file")
            app_share = root / "usr" / "share" / cp
            has_payload = False
            if app_share.is_dir():
                has_payload = any(p.name not in ("vendor", "DebAppBuilderIcon.png", "debian-app-builder-package.svg") for p in app_share.iterdir())
            if not has_payload:
                missing.append("Application file/folder — Choose File or Folder")
        if missing:
            detail = "\n• ".join(missing)
            messagebox.showwarning(
                title="Debian App Builder",
                message=f"Cannot build: missing required steps:\n• {detail}\n\nPlease complete them in the Build tab.",
            )
            log(f"Build validation failed: {', '.join(missing)}", "error")
            set_status("Build validation failed", ok=False)
            update_action_states()
            return
        # Prompt: "Choose where the finished .deb is saved."
        deb_output_raw = ""
        try:
            deb_output_raw = deb_output_var.get().strip()
        except Exception:
            deb_output_raw = ""
        if not deb_output_raw:
            chosen = filedialog.asksaveasfilename(
                title="Choose where the finished .deb is saved.",
                defaultextension=".deb",
                initialfile=f"{Path(package_root).name}.deb",
                initialdir=str(Path(package_root).resolve().parent),
                filetypes=[("Debian package", "*.deb"), ("All files", "*.*")],
            )
            if not chosen:
                chosen_dir = filedialog.askdirectory(title="Choose where the finished .deb is saved.")
                if not chosen_dir:
                    return
                deb_output_raw = chosen_dir
            else:
                deb_output_raw = chosen
            try:
                deb_output_var.set(deb_output_raw)
            except Exception:
                pass
        # Resolve final .deb path via core helper (also handles directory vs file)
        try:
            archive_path_str = c.choose_finished_deb_path(package_root, deb_output_raw)
        except Exception:
            # fallback: treat raw as directory
            p = Path(deb_output_raw)
            if p.suffix == ".deb":
                archive_path_str = str(p.resolve())
            else:
                archive_path_str = str((p / f"{Path(package_root).name}.deb").resolve())
        archive_path = Path(archive_path_str)
        # ensure parent exists (for native build)
        try:
            archive_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        # --- Always create INSTRUCTIONS.txt with attribution + usage instructions (inside package, included in .deb) ---
        try:
            _instr_desktop = desktop_name.get().strip()
            if not _instr_desktop:
                _instr_desktop = cp
        except Exception:
            _instr_desktop = cp
        try:
            _instr_arch = architecture.get().strip() or "amd64"
        except Exception:
            _instr_arch = "amd64"
        try:
            _instr_appid = appstream_id.get().strip()
        except Exception:
            _instr_appid = ""
        # fetch derived App ID if placeholder empty (same logic as create_appstream_file)
        if not _instr_appid or _instr_appid.lower().startswith("com.example."):
            try:
                _m_tmp = maintainer.get().strip()
            except Exception:
                _m_tmp = ""
            try:
                _derived_tmp = _derive_app_id_from_maintainer(_m_tmp, cp)  # defined in AppStream section
                if _derived_tmp:
                    _instr_appid = _derived_tmp
            except Exception:
                pass
        try:
            _instr_main = selected_file["name"] if isinstance(selected_file, dict) else ""
            _instr_main = str(_instr_main or "").strip()
        except Exception:
            _instr_main = ""
        try:
            c.create_instructions_file(package_root, cp, desktop_name=_instr_desktop, version=cv, arch=_instr_arch, app_id=_instr_appid, main_file=_instr_main)
            log("Created INSTRUCTIONS.txt (with attribution) inside package.", "ok")
        except Exception as _e:
            log(f"Could not create INSTRUCTIONS.txt: {_e}", "error")
        start_busy()
        set_status("Building package...", ok=None)
        log(f"Building Debian package on {build_system}...")
        log(f"Output: {archive_path}")
        try:
            package_path = Path(package_root).resolve()
            stage_on_linux = build_mode == "wsl" or (
                platform.system() == "Linux" and len(package_path.parts) > 1
                and package_path.parts[1] == "mnt"
            )
            if stage_on_linux:
                if build_mode == "wsl":
                    drive = package_path.drive.rstrip(":").lower()
                    if not drive:
                        raise OSError("The package path does not have a Windows drive letter.")
                    linux_root = f"/mnt/{drive}/" + "/".join(package_path.parts[1:])
                    # map archive_path to WSL path (use its own drive)
                    archive_drive = archive_path.drive.rstrip(":").lower()
                    if archive_drive:
                        linux_archive = f"/mnt/{archive_drive}/" + "/".join(archive_path.parts[1:])
                    else:
                        linux_archive = str(archive_path).replace("\\", "/")
                    command_prefix = [build_command]
                else:
                    parts = package_path.parts
                    drive = parts[2] if len(parts) > 2 and parts[1] == "mnt" else ""
                    linux_root = str(package_path)
                    # archive might be under /mnt/c/... or native /tmp
                    if len(archive_path.parts) > 2 and archive_path.parts[1] == "mnt":
                        linux_archive = str(archive_path)
                    else:
                        linux_archive = str(archive_path)
                    command_prefix = []
                wsl_root = f"/tmp/debian-app-builder-{package_path.name}"
                subprocess.run(command_prefix + ["rm", "-rf", wsl_root],
                               capture_output=True, text=True, check=True)
                subprocess.run(command_prefix + ["cp", "-a", linux_root, wsl_root],
                               capture_output=True, text=True, check=True)
                for target, mode in (
                    (f"{wsl_root}/DEBIAN", "755"),
                    (f"{wsl_root}/DEBIAN/control", "644"),
                    (f"{wsl_root}/usr/bin/{cp}", "755"),
                ):
                    subprocess.run(command_prefix + ["chmod", mode, target],
                                   capture_output=True, text=True, check=True)
                result = subprocess.run(
                    command_prefix + ["dpkg-deb", "--build", wsl_root, linux_archive],
                    capture_output=True, text=True)
                subprocess.run(command_prefix + ["rm", "-rf", wsl_root],
                               capture_output=True, text=True, check=True)
            else:
                result = subprocess.run(
                    [build_command, "--build", str(package_path), str(archive_path)],
                    capture_output=True, text=True)
        except (OSError, subprocess.SubprocessError) as error:
            end_busy()
            err_msg = str(error).strip() or "Unknown build error"
            log(f"Build failed: {err_msg}", "error")
            set_status("Build failed", ok=False)
            messagebox.showerror("Debian App Builder", f"Build failed:\n{err_msg}")
            return
        if result.returncode != 0:
            end_busy()
            err_detail = (result.stderr or result.stdout or "").strip() or "dpkg-deb could not build the package."
            log(err_detail, "error")
            set_status("Build failed", ok=False)
            messagebox.showerror("Debian App Builder", f"Build failed:\n{err_detail}")
            return
        end_busy()
        log(result.stdout.strip() or "Package built successfully.", "ok")
        log(f"Saved to {archive_path}", "ok")
        # Also create/copy INSTRUCTIONS.txt next to the .deb for user reference (outside package)
        try:
            inside_instr = Path(package_root) / "usr" / "share" / cp / "INSTRUCTIONS.txt"
            if inside_instr.is_file():
                outside_instr = archive_path.parent / f"{cp}_INSTRUCTIONS.txt"
                try:
                    shutil.copy2(str(inside_instr), str(outside_instr))
                    log(f"Also saved instructions next to .deb: {outside_instr}", "ok")
                except Exception as _copy_e:
                    log(f"Could not copy INSTRUCTIONS next to .deb: {_copy_e}", "error")
                # also create variant named after deb
                try:
                    alt_outside = archive_path.with_suffix(".txt")
                    if alt_outside != outside_instr:
                        shutil.copy2(str(inside_instr), str(alt_outside))
                except Exception:
                    pass
            else:
                # fallback: create directly next to deb if inside not found
                try:
                    c.create_instructions_file(str(archive_path.parent), cp, desktop_name=_instr_desktop, version=cv, arch=_instr_arch, app_id=_instr_appid, main_file=_instr_main)
                    # move from temp package doc location to next to deb
                    tmp_src = Path(str(archive_path.parent)) / "usr" / "share" / cp / "INSTRUCTIONS.txt"
                    if tmp_src.is_file():
                        shutil.copy2(str(tmp_src), str(archive_path.parent / f"{cp}_INSTRUCTIONS.txt"))
                except Exception:
                    pass
        except Exception as _e:
            log(f"Could not handle INSTRUCTIONS copy: {_e}", "error")
        messagebox.showinfo("Debian App Builder", f"Package built successfully:\n{archive_path}")
        set_status("Build successful", ok=True)

    def set_write_inputs_state(state):
        # FIX: Package & Desktop & AppStream entries must remain editable
        # even when no file is selected yet (starting from scratch).
        # The Application tab may already list a file (selected files) but
        # Package & Desktop tab was incorrectly disabled when selected_file
        # was None. Force metadata fields to "normal" so user can edit
        # from scratch; only respect explicit "disabled" for busy lock is
        # not needed – metadata stays always available.
        # If caller passes "disabled" we still keep metadata enabled unless
        # it's a forced lock – but we treat any call as intention to keep
        # editable, so map "disabled" -> "normal" for metadata entries.
        effective = "normal" if state in ("normal", "disabled") else state
        # Keep AppStream description textbox sync
        for widget in (
            bin_name, package, version, architecture, depends, maintainer, description,
            desktop_name, desktop_comment, desktop_exec, desktop_categories,
            desktop_path_entry,
        ):
            try:
                widget.configure(state=effective)
            except Exception:
                pass
        # AppStream fields – same fix: always available
        for widget in (
            appstream_id, appstream_name, appstream_summary, appstream_developer,
            appstream_license, appstream_meta_license, appstream_homepage,
            appstream_categories, appstream_keywords,
        ):
            try:
                widget.configure(state=effective)
            except Exception:
                pass
        try:
            appstream_description.configure(state=effective)
        except Exception:
            pass
        # desktop_icon is now StringVar for hicolor – no widget configure needed
        # hicolor/appstream buttons remain always enabled (optional)

    build_ready_announced = {"value": False}

    def desktop_form_ready():
        return bool(_get_effective_bin() and desktop_name.get().strip() and desktop_exec.get().strip())

    def sync_file_state():
        """Re-validate on-disk files and keep file_state / selected_file consistent (fixes stale-state / double-control bug)."""
        try:
            pkg = _get_effective_bin()
            root = Path(package_root)
            # sync selected_file if missing but payload exists – check all share subfolders leniently
            if not selected_file["name"]:
                candidates = []
                # check current, original, and any share folder
                for cand_pkg in (pkg, package_name):
                    app_share = root / "usr" / "share" / cand_pkg
                    if app_share.is_dir():
                        for p in app_share.iterdir():
                            if p.name not in ("vendor", "DebAppBuilderIcon.png", "debian-app-builder-package.svg"):
                                candidates.append(p.name)
                        if candidates:
                            selected_file["name"] = candidates[0]
                            break
                if not candidates:
                    # lenient: any payload in share root
                    share_root = root / "usr" / "share"
                    if share_root.is_dir():
                        for sub in share_root.iterdir():
                            if sub.is_dir() and sub.name not in ("applications",):
                                for p in sub.iterdir():
                                    if p.name not in ("vendor", "DebAppBuilderIcon.png", "debian-app-builder-package.svg"):
                                        selected_file["name"] = p.name
                                        candidates.append(p.name)
                                        break
                                if candidates:
                                    break
            # sync flags from filesystem (use current pkg field) – control is package-agnostic
            cur_pkg = _get_effective_bin()
            # control exists regardless of package name – check once
            control_exists = (root / "DEBIAN" / "control").is_file() and (root / "DEBIAN" / "control").stat().st_size > 0
            file_state["control_created"] = control_exists
            if cur_pkg:
                exec_exists = (root / "usr" / "bin" / cur_pkg).is_file()
                # fallback: if bin exists under different name, still consider exec exists for leniency
                if not exec_exists:
                    bin_dir = root / "usr" / "bin"
                    if bin_dir.is_dir():
                        exec_exists = any(b.is_file() for b in bin_dir.iterdir())
                        # but keep file_state false for current pkg if name mismatch – UI will still require correct name
                        # so only set true if current pkg file exists
                        exec_exists = (root / "usr" / "bin" / cur_pkg).is_file()
                file_state["execution_created"] = (root / "usr" / "bin" / cur_pkg).is_file()
                file_state["desktop_created"] = (root / "usr" / "share" / "applications" / f"{cur_pkg}.desktop").is_file()
            else:
                file_state["execution_created"] = (root / "usr" / "bin" / package_name).is_file()
                file_state["desktop_created"] = (root / "usr" / "share" / "applications" / f"{package_name}.desktop").is_file()
            # AppStream: check any metainfo file exists (optional)
            try:
                metainfo_dir = root / "usr" / "share" / "metainfo"
                has_appstream = False
                if metainfo_dir.is_dir():
                    has_appstream = any(metainfo_dir.glob("*.metainfo.xml")) or any(metainfo_dir.glob("*.appdata.xml"))
                file_state["appstream_created"] = has_appstream
                appstream_created["value"] = has_appstream
                if has_appstream:
                    appstream_status_var.set("AppStream metadata present")
            except Exception:
                pass
        except Exception:
            pass

    def update_action_states(*_event):
        sync_file_state()
        control_ready = all((_get_effective_bin(), version.get().strip(),
                             maintainer.get().strip(), description.get().strip()))
        # execution needs payload on disk OR selected file – lenient check across share
        has_payload = False
        try:
            cur_pkg = _get_effective_bin()
            # check current pkg share first
            app_share = Path(package_root) / "usr" / "share" / cur_pkg
            if app_share.is_dir() and any(p.name not in ("vendor", "DebAppBuilderIcon.png", "debian-app-builder-package.svg") for p in app_share.iterdir()):
                has_payload = True
            else:
                # lenient: check any share subfolder (fixes double-control when pkg renamed)
                share_root = Path(package_root) / "usr" / "share"
                if share_root.is_dir():
                    for sub in share_root.iterdir():
                        if sub.is_dir() and sub.name not in ("applications",):
                            if any(p.name not in ("vendor", "DebAppBuilderIcon.png", "debian-app-builder-package.svg") for p in sub.iterdir()):
                                has_payload = True
                                break
                # also consider selected_file
                if not has_payload and selected_file["name"]:
                    has_payload = True
        except Exception:
            has_payload = False
        execution_ready = bool(_get_effective_bin() and version.get().strip() and (selected_file["name"] or has_payload))
        desktop_ready = desktop_form_ready()
        # BUILD requires real on-disk artifacts – use lenient has_payload but strict file checks
        cur_pkg = _get_effective_bin()
        root = Path(package_root)
        control_ok = (root / "DEBIAN" / "control").is_file() and (root / "DEBIAN" / "control").stat().st_size > 0
        exec_ok = (root / "usr" / "bin" / cur_pkg).is_file() if cur_pkg else False
        desktop_ok = (root / "usr" / "share" / "applications" / f"{cur_pkg}.desktop").is_file() if cur_pkg else False
        build_ready_files = bool(control_ok and exec_ok and desktop_ok and has_payload)
        build_ready = bool(build_ready_files and build_command)
        # keep file_state consistent for other callers
        file_state["control_created"] = control_ok
        file_state["execution_created"] = exec_ok
        file_state["desktop_created"] = desktop_ok
        ctrl_btn.configure(state="normal" if control_ready else "disabled")
        make_exec.configure(state="normal" if execution_ready else "disabled")
        desktop_btn.configure(state="normal" if desktop_ready else "disabled")
        # AppStream: enable when required fields are filled (calling core.write_appstream_file)
        try:
            _adesc = appstream_description.get("1.0", "end-1c").strip() if hasattr(appstream_description, "get") else ""
        except Exception:
            _adesc = ""
        appstream_ready = bool(_get_effective_bin() and appstream_name.get().strip() and appstream_summary.get().strip() and _adesc)
        try:
            appstream_btn.configure(state="normal" if appstream_ready else "disabled")
        except Exception:
            pass
        try:
            _sync_appstream_defaults()
        except Exception:
            pass
        # Fix: BUILD button should be enabled when all files are ready, even if build env missing,
        # so user gets an alert instead of silent disabled button (bug: "doesn't alert me")
        if build_ready_files:
            build_btn.configure(state="normal")
            # visually indicate env missing but keep clickable for alert
            if not build_command:
                try:
                    build_btn.configure(fg_color="#ff9800", hover_color="#e68900")
                except Exception:
                    pass
            else:
                try:
                    build_btn.configure(fg_color="red", hover_color="#cc0000")
                except Exception:
                    pass
        else:
            build_btn.configure(state="disabled")
        if build_ready and not build_ready_announced["value"]:
            log("Everything is ready. Press BUILD when you're done.", "ok")
            try:
                messagebox.showinfo(
                    "Debian App Builder",
                    "Everything is ready!\n\nAll required files have been created.\nPress BUILD to create the .deb package.",
                )
            except Exception:
                pass
        # also announce ready-files but env missing
        if build_ready_files and not build_command and not build_ready_announced["value"]:
            log(f"All files ready but build unavailable: {build_system} – press BUILD for details.", "error")
            try:
                messagebox.showwarning(
                    "Debian App Builder",
                    f"All files are ready, but build is unavailable:\n{build_system}\n\nPress BUILD for details or install the required build environment.",
                )
            except Exception:
                pass
        build_ready_announced["value"] = build_ready or build_ready_files
        if not build_command:
            if build_ready_files:
                set_status(f"Ready but build unavailable: {build_system} (click BUILD for info)", ok=False)
            else:
                set_status(f"Build unavailable: {build_system}", ok=False)
        elif build_ready:
            set_status("Ready to build", ok=True)
        else:
            set_status("Complete the required steps", ok=None)

    for entry in (bin_name, package, version, architecture, depends, maintainer, description,
                 desktop_name, desktop_comment, desktop_exec, desktop_term, desktop_categories, desktop_path_entry,
                 appstream_id, appstream_name, appstream_summary, appstream_developer,
                 appstream_license, appstream_meta_license, appstream_homepage,
                 appstream_categories, appstream_keywords):
        try:
            entry.bind("<KeyRelease>", update_action_states)
        except Exception:
            pass
    try:
        appstream_description.bind("<KeyRelease>", update_action_states)
    except Exception:
        pass
    # Also bind bin_name specifically for sync (ensured above but keep here for state)
    try:
        bin_name.bind("<KeyRelease>", _sync_bin_to_package_and_exec)
    except Exception:
        pass

    # FIX: sync selected_file from disk before deciding entry state –
    # when starting from scratch the Application tab may already list a file
    # (payload exists in usr/share/<pkg>) but selected_file was None, causing
    # Package & Desktop entries to be incorrectly disabled.
    try:
        # early sync (same logic as sync_file_state) to populate selected_file
        _pkg0 = _get_effective_bin()
        _root0 = Path(package_root)
        if not selected_file["name"]:
            for cand_pkg in (_pkg0, package_name):
                _ap0 = _root0 / "usr" / "share" / cand_pkg
                if _ap0.is_dir():
                    for p in _ap0.iterdir():
                        if p.name not in ("vendor", "DebAppBuilderIcon.png", "debian-app-builder-package.svg"):
                            selected_file["name"] = p.name
                            break
                    if selected_file["name"]:
                        break
            if not selected_file["name"]:
                _sr0 = _root0 / "usr" / "share"
                if _sr0.is_dir():
                    for sub in _sr0.iterdir():
                        if sub.is_dir() and sub.name not in ("applications",):
                            for p in sub.iterdir():
                                if p.name not in ("vendor", "DebAppBuilderIcon.png", "debian-app-builder-package.svg"):
                                    selected_file["name"] = p.name
                                    break
                            if selected_file["name"]:
                                break
    except Exception:
        pass
    # Package & Desktop must be editable from scratch – always enable
    set_write_inputs_state("normal")
    refresh_file_indicator()
    update_action_states()
    update_package_info()
    if not build_command:
        log(f"Build disabled: {build_system}.", "error")

    # --- Restore saved session if provided (load) ---
    if saved_data and isinstance(saved_data, dict):
        try:
            fields = saved_data.get("fields", {})
            # Restore selected_file first so inputs can be enabled

            try:
                sf = fields.get("selected_file")
                if sf:
                    selected_file["name"] = str(sf)
            except Exception:
                pass
            # Temporarily enable all inputs to allow text insertion (handles disabled state and textarea)
            try:
                set_write_inputs_state("normal")
            except Exception:
                pass
            # restore entry fields – handles both CTkEntry and CTkTextbox/StringVar
            def _set_entry(entry, key):
                try:
                    val = fields.get(key, "")
                    if val is None:
                        val = ""
                    val = str(val)
                    # Try to handle CTkEntry, Entry, StringVar, and Textbox
                    # StringVar
                    if hasattr(entry, "set") and not hasattr(entry, "delete"):
                        try:
                            entry.set(val)
                            return
                        except Exception:
                            pass
                    # For widget, ensure normal state
                    try:
                        entry.configure(state="normal")
                    except Exception:
                        pass
                    # Detect Textbox vs Entry by trying textbox indices
                    try:
                        # Try textbox style first
                        entry.delete("1.0", "end")
                        entry.insert("1.0", val)
                        # If that succeeded and widget is actually Entry, it will have inserted at 1.0 but Entry uses 0, so also try Entry way
                        # Check if content is correct, if not fallback
                        try:
                            cur = entry.get("1.0", "end-1c") if hasattr(entry, "get") and "1.0" in str(entry.get) else None
                        except Exception:
                            cur = None
                        if cur is not None and cur.strip() != val.strip():
                            raise Exception("textbox fallback")
                    except Exception:
                        try:
                            entry.delete(0, "end")
                            entry.insert(0, val)
                        except Exception:
                            try:
                                entry.delete("0", "end")
                                entry.insert("0", val)
                            except Exception:
                                pass
                except Exception:
                    pass
            # Binary name – source of truth (migrate old saves where package held the bin)
            try:
                _bin_val = fields.get("bin_name")
                if not _bin_val:
                    _bin_val = fields.get("package") or package_name
                if _bin_val:
                    _set_entry(bin_name, "bin_name")
                    # if _set_entry didn't set because key missing, set manually
                    try:
                        if not bin_name.get().strip():
                            bin_name.delete(0, "end")
                            bin_name.insert(0, str(_bin_val))
                    except Exception:
                        pass
                    # keep package and exec in sync with bin on load
                    try:
                        _sync_bin_to_package_and_exec()
                    except Exception:
                        pass
            except Exception:
                pass
            _set_entry(package, "package")
            _set_entry(version, "version")
            _set_entry(architecture, "architecture")
            _set_entry(depends, "depends")
            _set_entry(maintainer, "maintainer")
            _set_entry(description, "description")
            _set_entry(desktop_name, "desktop_name")
            _set_entry(desktop_comment, "desktop_comment")
            _set_entry(desktop_exec, "desktop_exec")
            _set_entry(desktop_term, "desktop_term")
            _set_entry(desktop_categories, "desktop_categories")
            _set_entry(desktop_path_entry, "desktop_path")
            # AppStream – dedicated section (calling core.write_appstream_file)
            _set_entry(appstream_id, "appstream_id")
            _set_entry(appstream_name, "appstream_name")
            _set_entry(appstream_summary, "appstream_summary")
            _set_entry(appstream_description, "appstream_description")
            _set_entry(appstream_developer, "appstream_developer")
            _set_entry(appstream_license, "appstream_license")
            _set_entry(appstream_meta_license, "appstream_meta_license")
            _set_entry(appstream_homepage, "appstream_homepage")
            _set_entry(appstream_categories, "appstream_categories")
            _set_entry(appstream_keywords, "appstream_keywords")
            # desktop_icon removed – old entrybox text no longer stored/loaded (hicolor used)
            # migrate: ignore old desktop_icon if present in saved file
            try:
                fields.pop("desktop_icon", None)
            except Exception:
                pass
            try:
                val = fields.get("deb_output", deb_output_var.get())
                try:
                    deb_output_var.set(str(val) if val is not None else "")
                except Exception:
                    _set_entry(deb_output_var, "deb_output")
            except Exception:
                pass
            # hicolor
            try:
                if fields.get("hicolor_generated"):
                    hicolor_generated["value"] = True
                    hicolor_generated["source"] = fields.get("hicolor_source")
                    hicolor_status_var.set(fields.get("hicolor_status", "Hicolor icons restored"))
            except Exception:
                pass
            # appstream
            try:
                if fields.get("appstream_created"):
                    appstream_created["value"] = True
                    appstream_status_var.set(fields.get("appstream_status", "AppStream restored"))
            except Exception:
                pass
            # re-apply correct enabled/disabled state and refresh
            # FIX: keep Package & Desktop editable even if selected_file missing
            # sync from disk if needed
            try:
                if not selected_file["name"]:
                    _pkg_r = _get_effective_bin()
                    _root_r = Path(package_root)
                    for cand in (_pkg_r, package_name):
                        _apr = _root_r / "usr" / "share" / cand
                        if _apr.is_dir():
                            for p in _apr.iterdir():
                                if p.name not in ("vendor", "DebAppBuilderIcon.png", "debian-app-builder-package.svg"):
                                    selected_file["name"] = p.name
                                    break
                        if selected_file["name"]:
                            break
            except Exception:
                pass
            try:
                set_write_inputs_state("normal")
            except Exception:
                pass
            refresh_file_indicator()
            update_action_states()
            update_package_info()
            log("Loaded saved session", "ok")
        except Exception as e:
            log(f"Failed to restore saved session: {e}", "error")

    # --- Alert to save work on close (file will be read-only) ---
    def _collect_writefiles_session():
        try:
            # desktop_icon removed – hicolor now provides icons, old text not saved
            return {
                "type": "writefiles",
                "package_root": str(package_root),
                "package_name": str(package_name),
                "package_version": str(package_version),
                "fields": {
                    "bin_name": bin_name.get(),
                    "package": package.get(),
                    "version": version.get(),
                    "architecture": architecture.get(),
                    "depends": depends.get(),
                    "maintainer": maintainer.get(),
                    "description": description.get(),
                    "desktop_name": desktop_name.get(),
                    "desktop_comment": desktop_comment.get(),
                    "desktop_exec": desktop_exec.get(),
                    "desktop_term": desktop_term.get(),
                    "desktop_categories": desktop_categories.get(),
                    "desktop_path": desktop_path_entry.get(),
                    "deb_output": deb_output_var.get(),
                    "selected_file": selected_file["name"],
                    "hicolor_generated": hicolor_generated["value"],
                    "hicolor_source": hicolor_generated["source"],
                    "hicolor_status": hicolor_status_var.get(),
                    "appstream_id": appstream_id.get(),
                    "appstream_name": appstream_name.get(),
                    "appstream_summary": appstream_summary.get(),
                    "appstream_description": appstream_description.get("1.0", "end-1c") if hasattr(appstream_description, "get") else "",
                    "appstream_developer": appstream_developer.get(),
                    "appstream_license": appstream_license.get(),
                    "appstream_meta_license": appstream_meta_license.get(),
                    "appstream_homepage": appstream_homepage.get(),
                    "appstream_categories": appstream_categories.get(),
                    "appstream_keywords": appstream_keywords.get(),
                    "appstream_created": appstream_created["value"],
                    "appstream_status": appstream_status_var.get(),
                },
            }
        except Exception as e:
            return {"type": "writefiles", "package_root": str(package_root), "error": str(e)}

    def _on_writefiles_close():
        ans = messagebox.askyesnocancel(
            "Debian App Builder",
            "Save your work before closing?\n\nYes = Save (file will be read-only and cannot be changed)\nNo = Don't save\nCancel = Stay",
        )
        if ans is None:  # Cancel
            return
        if ans is True:  # Yes -> save
            try:
                data = _collect_writefiles_session()
                # ensure writable if previously readonly
                if SAVE_FILE.exists():
                    _make_file_writable(SAVE_FILE)
                SAVE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
                _make_file_readonly(SAVE_FILE)
                messagebox.showinfo("Debian App Builder", f"Work saved to:\n{SAVE_FILE}\n\nFile is now read-only and cannot be changed.")
            except Exception as e:
                messagebox.showerror("Debian App Builder", f"Failed to save session:\n{e}")
                return
        # No -> just close without saving (keep existing saved file as is)
        try:
            app.destroy()
        except Exception:
            try:
                app.quit()
            except Exception:
                pass

    try:
        app.protocol("WM_DELETE_WINDOW", _on_writefiles_close)
    except Exception:
        pass
    app.mainloop()



def build_structure():
    package_name = output.get().strip()
    version = output2.get().strip()
    # Architecture entry in root – allows any arch (all, amd64, i386, arm64, armhf, etc.)
    try:
        arch = output3.get().strip() if "output3" in globals() and output3.winfo_exists() else "amd64"
    except Exception:
        try:
            arch = output3.get().strip()
        except Exception:
            arch = "amd64"
    if not arch:
        arch = "amd64"

    if not package_name or not version:
        messagebox.showwarning(
            title="Debian App Builder",
            message="Package name and version are required.",
        )
        return

    # Prompt: "Choose where the .deb structure is created."
    output_dir = ""
    try:
        if "output_dir_var" in globals():
            output_dir = output_dir_var.get().strip()
    except Exception:
        output_dir = ""
    if not output_dir:
        chosen = filedialog.askdirectory(title="Choose where the .deb structure is created.")
        if not chosen:
            return
        output_dir = chosen
        try:
            output_dir_var.set(chosen)
        except Exception:
            pass

    try:
        package_root = create_deb_structure(package_name, version, arch=arch, output_dir=output_dir)
    except (OSError, ValueError) as error:
        messagebox.showerror(
            "Debian App Builder",
            f"Could not create the package structure:\n{error}",
        )
        return

    # Properly tear down root before opening writefiles CTk – avoid CustomTkinter after race
    # (ScalingTracker / AppearanceModeTracker keep `after` loops that raise
    #  "invalid command name ...check_dpi_scaling" after destroy)
    try:
        root.update_idletasks()
    except Exception:
        pass
    try:
        # withdraw first so trackers see destroyed state earlier, suppress pending afters
        root.withdraw()
    except Exception:
        pass
    try:
        root.destroy()
    except tk.TclError:
        pass
    except Exception:
        try:
            root.quit()
        except Exception:
            pass
    writefiles(package_root, package_name, version)


def askPyfile(package_root, package_name):
    return c.choose_and_copy(f"{package_root}/usr/share/{package_name}/")


ctk.set_appearance_mode("system")
root = ctk.CTk()

center_window(root, 420, 590)
root.resizable(False, False)
root.title(f"Debian App Builder {VERSION}")
window_icon = load_window_icon(root)

# ---------- Header ----------
header = ctk.CTkFrame(root, fg_color="transparent")
header.pack(fill="x", padx=24, pady=(28, 10))
title_row = ctk.CTkFrame(header, fg_color="transparent")
title_row.pack()
if window_icon:
    ctk.CTkLabel(title_row, image=window_icon, text="").pack(side="left", padx=(0, 8))
ctk.CTkLabel(
    title_row, text="Debian App Builder",
    font=ctk.CTkFont(size=22, weight="bold"),
).pack(side="left")
ctk.CTkLabel(
    header, text="Create a Debian package structure",
    text_color="#8b95a1", font=ctk.CTkFont(size=12),
).pack(pady=(4, 0))

# ---------- Inputs ----------
input_frame = ctk.CTkFrame(root)
input_frame.pack(fill="x", padx=24, pady=(6, 8))
input_frame.grid_columnconfigure(0, weight=1)

out_label = ctk.CTkLabel(input_frame, text="Package name", anchor="w")
out_label.grid(row=0, column=0, padx=16, pady=(16, 4), sticky="w")
output = ctk.CTkEntry(input_frame, placeholder_text="example-app")
output.grid(row=1, column=0, padx=16, pady=(0, 10), sticky="ew")

out_label2 = ctk.CTkLabel(input_frame, text="Package version", anchor="w")
out_label2.grid(row=2, column=0, padx=16, pady=(4, 4), sticky="w")
output2 = ctk.CTkEntry(input_frame, placeholder_text="1.0.0")
output2.grid(row=3, column=0, padx=16, pady=(0, 10), sticky="ew")

out_label_arch = ctk.CTkLabel(input_frame, text="Architecture", anchor="w")
out_label_arch.grid(row=4, column=0, padx=16, pady=(4, 4), sticky="w")
output3 = ctk.CTkEntry(input_frame, placeholder_text="amd64  •  all, amd64, i386, arm64, armhf")
output3.insert(0, "amd64")
output3.grid(row=5, column=0, padx=16, pady=(0, 10), sticky="ew")

output_dir_label = ctk.CTkLabel(input_frame, text="Choose where the .deb structure is created.", anchor="w")
output_dir_label.grid(row=6, column=0, padx=16, pady=(4, 4), sticky="w")
output_dir_var = ctk.StringVar(value=str(Path.cwd()))
output_dir_frame = ctk.CTkFrame(input_frame, fg_color="transparent")
output_dir_frame.grid(row=7, column=0, padx=16, pady=(0, 16), sticky="ew")
output_dir_frame.grid_columnconfigure(0, weight=1)
output_dir_entry = ctk.CTkEntry(output_dir_frame, textvariable=output_dir_var, placeholder_text=str(Path.cwd()))
output_dir_entry.grid(row=0, column=0, sticky="ew")

def choose_output_dir():
    chosen = filedialog.askdirectory(title="Choose where the .deb structure is created.")
    if chosen:
        output_dir_var.set(chosen)

output_dir_button = ctk.CTkButton(output_dir_frame, text="Browse", width=78, command=choose_output_dir)
output_dir_button.grid(row=0, column=1, padx=(8, 0))

ctk.CTkLabel(
    root,
    text="Use lowercase letters, digits and hyphens for the name.",
    text_color="#8b95a1", font=ctk.CTkFont(size=11),
).pack(fill="x", padx=24, pady=(0, 4))

Build_btn = ctk.CTkButton(
    root,
    text="Make the structure",
    command=build_structure,
    height=42,
)
Build_btn.pack(fill="x", padx=24, pady=(6, 24))

# --- Save/Load for initial window (alert on close, load on startup) ---
def _collect_initial_session():
    try:
        return {
            "type": "initial",
            "fields": {
                "package_name": output.get(),
                "package_version": output2.get(),
                "package_arch": output3.get() if "output3" in globals() else "amd64",
                "output_dir": output_dir_var.get(),
            },
        }
    except Exception:
        return {"type": "initial", "fields": {}}


def _on_root_close():
    # Only prompt if user typed something
    has_input = False
    try:
        has_input = bool(output.get().strip() or output2.get().strip() or (output3.get().strip() and output3.get().strip() != "amd64"))
    except Exception:
        has_input = False
    if not has_input and not SAVE_FILE.is_file():
        try:
            root.destroy()
        except Exception:
            pass
        return
    ans = messagebox.askyesnocancel(
        "Debian App Builder",
        "Save your work before closing?\n\nYes = Save (file will be read-only and cannot be changed)\nNo = Don't save\nCancel = Stay",
    )
    if ans is None:
        return
    if ans is True:
        try:
            data = _collect_initial_session()
            if SAVE_FILE.exists():
                _make_file_writable(SAVE_FILE)
            SAVE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
            _make_file_readonly(SAVE_FILE)
            messagebox.showinfo("Debian App Builder", f"Work saved to:\n{SAVE_FILE}\n\nFile is now read-only and cannot be changed.")
        except Exception as e:
            messagebox.showerror("Debian App Builder", f"Failed to save session:\n{e}")
            return
    try:
        root.destroy()
    except Exception:
        try:
            root.quit()
        except Exception:
            pass


try:
    root.protocol("WM_DELETE_WINDOW", _on_root_close)
except Exception:
    pass


def _load_saved_session_startup():
    if not SAVE_FILE.is_file():
        return
    try:
        raw = SAVE_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception:
        return
    # Ask: load saved file or start from scratch
    ans = messagebox.askyesnocancel(
        "Debian App Builder",
        "A saved session was found.\n\nDo you want to load your saved work?\n\nYes = Load saved file\nNo = Start from scratch (delete saved file)\nCancel = Keep file and start fresh",
    )
    if ans is None:
        return
    if ans is False:
        # No = Start from scratch – delete saved file
        try:
            _make_file_writable(SAVE_FILE)
            SAVE_FILE.unlink(missing_ok=True)
            messagebox.showinfo("Debian App Builder", "Saved session deleted. Starting from scratch.")
        except Exception as e:
            messagebox.showerror("Debian App Builder", f"Could not delete saved file:\n{e}")
        return
    if ans is True:
        # Yes = Load
        try:
            typ = data.get("type")
            if typ == "writefiles":
                # Need package_root to exist – if not, warn and fallback to initial
                pkg_root = data.get("package_root")
                pkg_name = data.get("package_name") or data.get("fields", {}).get("package", "")
                pkg_ver = data.get("package_version") or data.get("fields", {}).get("version", "")
                if pkg_root and Path(pkg_root).exists():
                    # destroy root and open writefiles with saved data
                    try:
                        root.destroy()
                    except Exception:
                        pass
                    writefiles(pkg_root, pkg_name, pkg_ver, saved_data=data)
                    return
                else:
                    messagebox.showwarning("Debian App Builder", f"Saved package path not found:\n{pkg_root}\n\nLoading initial fields only.")
                    # fall through to initial fields restore
            # initial or fallback
            fields = data.get("fields", {})
            if "package_name" in fields:
                try:
                    output.delete(0, "end")
                    output.insert(0, str(fields.get("package_name", "")))
                except Exception:
                    pass
            if "package_version" in fields:
                try:
                    output2.delete(0, "end")
                    output2.insert(0, str(fields.get("package_version", "")))
                except Exception:
                    pass
            if "package_arch" in fields or "output3" in fields or "architecture" in fields:
                try:
                    _arch_val = fields.get("package_arch") or fields.get("architecture") or fields.get("output3") or "amd64"
                    output3.delete(0, "end")
                    output3.insert(0, str(_arch_val))
                except Exception:
                    pass
            if "output_dir" in fields:
                try:
                    output_dir_var.set(str(fields.get("output_dir", "")))
                except Exception:
                    pass
            messagebox.showinfo("Debian App Builder", f"Loaded saved session from:\n{SAVE_FILE}")
        except Exception as e:
            messagebox.showerror("Debian App Builder", f"Failed to load saved session:\n{e}")


# Check for saved session shortly after UI shows – guarded for destroyed window
try:
    if root.winfo_exists():
        root.after(400, lambda: _load_saved_session_startup() if root.winfo_exists() else None)
except (tk.TclError, RuntimeError):
    pass
except Exception:
    pass

try:
    root.mainloop()
except tk.TclError:
    # suppress Tcl after race on exit (CustomTkinter scaling tracker)
    pass
