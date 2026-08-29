import os
import platform
import shutil
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
import customtkinter as ctk
import core as c
from core import create_deb_structure

SCRIPT_DIR = Path(__file__).resolve().parent
ICON_CANDIDATES = [
    SCRIPT_DIR / "DebAppBuilderIcon.png",
    SCRIPT_DIR.parent / "DebAppBuilderLogo.png",
]
ICON_PATH = next((p for p in ICON_CANDIDATES if p.exists()), ICON_CANDIDATES[0])
if platform.system() == "Windows":
    WINDOW_ICON_PATH = ICON_PATH.with_suffix(".ico")
print('''THIS PROJECT IS OPEN-SOURCE, YOU CAN MODIFY, DISTRIBUTE AND USE IT FREELY.\nHowever you must credit the original author and the project repository if you use it in your own project.\nSincerely Tuffgit21 site:https://tuffgit21.github.io/\nGithub repository:https://github.com/tuffgit21/Debian-App-Builder/ 
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


def load_window_icon(window):
    icon = None
    if ICON_PATH.exists() and ICON_PATH.suffix in (".png", ".gif", ".ppm", ".pgm"):
        try:
            icon = tk.PhotoImage(file=str(ICON_PATH))
        except tk.TclError:
            icon = None
    if platform.system() == "Windows" and WINDOW_ICON_PATH.exists():
        try:
            window.iconbitmap(default=str(WINDOW_ICON_PATH))
        except tk.TclError:
            if icon is not None:
                window.iconphoto(True, icon)
    elif icon is not None:
        window.iconphoto(True, icon)
    window.window_icon = icon
    return icon.subsample(15, 15) if icon is not None else None

def center_window(window, width, height):
    """Calculates display resolution and centers the window on screen."""
    window.update_idletasks()
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    x = (screen_width // 2) - (width // 2)
    y = (screen_height // 2) - (height // 2)
    window.geometry(f"{width}x{height}+{x}+{y}")
def writefiles(package_root, package_name, package_version=""):
    build_mode, build_command, build_system = get_build_environment()
    ctk.set_appearance_mode("system")
    app = ctk.CTk()
    screen_w = app.winfo_screenwidth()
    screen_h = app.winfo_screenheight()
    win_w = min(560, max(440, screen_w - 40))
    win_h = min(640, max(480, screen_h - 60))
    center_window(app, win_w, win_h)
    app.title("Debian App Builder (WRITE MODE)")
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
    }
    info_values = {
        "location": ctk.StringVar(value=str(Path(package_root).resolve())),
        "files": ctk.StringVar(),
        "directories": ctk.StringVar(),
        "application": ctk.StringVar(value="Not selected"),
    }

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

    package_label = ctk.CTkLabel(metadata_frame, text="Package:", anchor="w")
    package_label.grid(row=0, column=0, padx=(16, 10), pady=(16, 6), sticky="w")
    package = ctk.CTkEntry(metadata_frame)
    package.insert(0, package_name)
    package.grid(row=0, column=1, padx=(0, 16), pady=(16, 6), sticky="ew")

    version_label = ctk.CTkLabel(metadata_frame, text="Version:", anchor="w")
    version_label.grid(row=1, column=0, padx=(16, 10), pady=6, sticky="w")
    version = ctk.CTkEntry(metadata_frame)
    if package_version:
        version.insert(0, package_version)
    version.grid(row=1, column=1, padx=(0, 16), pady=6, sticky="ew")

    architecture_label = ctk.CTkLabel(metadata_frame, text="Architecture:", anchor="w")
    architecture_label.grid(row=2, column=0, padx=(16, 10), pady=6, sticky="w")
    architecture = ctk.CTkEntry(metadata_frame)
    architecture.insert(0, "amd64")
    architecture.grid(row=2, column=1, padx=(0, 16), pady=6, sticky="ew")

    depends_label = ctk.CTkLabel(metadata_frame, text="Depends:", anchor="w")
    depends_label.grid(row=3, column=0, padx=(16, 10), pady=6, sticky="w")
    depends = ctk.CTkEntry(metadata_frame)
    depends.grid(row=3, column=1, padx=(0, 16), pady=6, sticky="ew")

    maintainer_label = ctk.CTkLabel(metadata_frame, text="Maintainer:", anchor="w")
    maintainer_label.grid(row=4, column=0, padx=(16, 10), pady=6, sticky="w")
    maintainer = ctk.CTkEntry(metadata_frame)
    maintainer.grid(row=4, column=1, padx=(0, 16), pady=6, sticky="ew")

    description_label = ctk.CTkLabel(metadata_frame, text="Description:", anchor="w")
    description_label.grid(row=5, column=0, padx=(16, 10), pady=(6, 16), sticky="w")
    description = ctk.CTkEntry(metadata_frame)
    description.grid(row=5, column=1, padx=(0, 16), pady=(6, 16), sticky="ew")

    ctk.CTkLabel(
        meta_scroll, text="Desktop Entry",
        font=ctk.CTkFont(size=13, weight="bold"),
        text_color="#c9a15a", anchor="w",
    ).pack(anchor="w", padx=18, pady=(14, 4))
    ctk.CTkLabel(
        meta_scroll, text=f"File: {package_name}.desktop", anchor="w",
        text_color="#8b95a1",
    ).pack(anchor="w", padx=18, pady=(0, 6))
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
    desktop_categories_label.grid(row=4, column=0, padx=(16, 10), pady=(6, 16), sticky="w")
    desktop_categories = ctk.CTkEntry(desktop_frame)
    desktop_categories.insert(0, "Utility")
    desktop_categories.grid(row=4, column=1, padx=(0, 16), pady=(6, 16), sticky="ew")

    desktop_icon_label = ctk.CTkLabel(desktop_frame, text="Icon:", anchor="w")
    desktop_icon_label.grid(row=5, column=0, padx=(16, 10), pady=(6, 16), sticky="w")
    desktop_icon_frame = ctk.CTkFrame(desktop_frame, fg_color="transparent")
    desktop_icon_frame.grid(row=5, column=1, padx=(0, 16), pady=(6, 16), sticky="ew")
    desktop_icon_frame.grid_columnconfigure(0, weight=1)
    desktop_icon = ctk.CTkEntry(desktop_icon_frame, placeholder_text="Optional icon name or path")
    desktop_icon.insert(0, f"/usr/share/{package_name}/DebAppBuilderIcon.png")
    desktop_icon.grid(row=0, column=0, sticky="ew")
    desktop_icon_button = ctk.CTkButton(
        desktop_icon_frame, text="Browse", width=78, command=lambda: choose_desktop_icon())
    desktop_icon_button.grid(row=0, column=1, padx=(8, 0))

    # ================= TAB 3: Build =================
    section(tab_build, "Actions")
    ctrl_btn = ctk.CTkButton(tab_build, text="Create Control file", command=lambda: create_control_file())
    ctrl_btn.pack(fill="x", padx=16, pady=(0, 8))
    make_exec = ctk.CTkButton(tab_build, text="Create Execution file", command=lambda: create_execution_file())
    make_exec.pack(fill="x", padx=16, pady=(0, 8))
    desktop_btn = ctk.CTkButton(
        tab_build, text=f"Create {package_name}.desktop file",
        command=lambda: create_desktop_file(), state="disabled")
    desktop_btn.pack(fill="x", padx=16, pady=(0, 8))
    build_btn = ctk.CTkButton(
        tab_build, text="⚠  BUILD  ⚠", command=lambda: build_package(),
        fg_color="red", text_color="black", hover_color="#cc0000")
    build_btn.pack(fill="x", padx=16, pady=(0, 14))

    section(tab_build, "Progress")
    progress = ctk.CTkProgressBar(tab_build)
    progress.pack(fill="x", padx=16, pady=(0, 10))
    progress.set(0)

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
        for b in (select_button, vendor_button, ctrl_btn, make_exec, desktop_btn, build_btn):
            b.configure(state="disabled")
        progress.configure(mode="indeterminate")
        progress.start()

    def end_busy():
        progress.stop()
        progress.configure(mode="determinate")
        progress.set(0)
        select_button.configure(state="normal")
        vendor_button.configure(state="normal")
        update_action_states()

    def choose_python_file():
        selected_name = askPyfile(package_root, package_name)
        if selected_name:
            selected_file["name"] = selected_name
        set_write_inputs_state("normal" if selected_file["name"] else "disabled")
        update_action_states()
        update_package_info()
        refresh_file_indicator()

    def vendor_pkgs():
        c.vendor_dependencies(package_root, package_name)
        update_package_info()
        log("Vendor dependencies bundled.", "ok")

    def refresh_file_indicator():
        for child in file_list_frame.winfo_children():
            child.destroy()
        application_path = Path(package_root) / "usr" / "share" / package_name
        files = sorted(path for path in application_path.iterdir()
                       if path.name != "vendor" and path.name != "DebAppBuilderIcon.png") \
            if application_path.exists() else []
        if not files:
            ctk.CTkLabel(file_list_frame, text="No application files selected",
                         text_color="gray").pack(anchor="w")
            file_list_frame.configure(height=60)
            return
        for file_path in files:
            file_row = ctk.CTkFrame(file_list_frame, fg_color="transparent")
            file_row.pack(fill="x", pady=2)
            ctk.CTkLabel(file_row, text=file_path.name, anchor="w").pack(
                side="left", fill="x", expand=True)
            size_str = "Folder" if file_path.is_dir() else format_file_size(file_path.stat().st_size)
            ctk.CTkLabel(file_row, text=size_str, width=70).pack(side="left", padx=6)
            ctk.CTkButton(file_row, text="X", width=28, height=24,
                          command=lambda path=file_path: remove_application_file(path)).pack(side="right")
        file_list_frame.configure(height=min(280, 60 + len(files) * 34))

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
            set_write_inputs_state("disabled")
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
        icon_path = filedialog.askopenfilename(
            title="Select desktop icon",
            filetypes=[("Image files", "*.png *.ico *.xpm"), ("All files", "*.*")],
        )
        if icon_path:
            desktop_icon.delete(0, "end")
            desktop_icon.insert(0, icon_path)
            update_action_states()

    def create_control_file():
        cp = package.get().strip()
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
        messagebox.showinfo("Debian App Builder", "Successfully created DEBIAN/control.")
        log("Created DEBIAN/control.", "ok")
        file_state["control_created"] = True
        update_action_states()
        update_package_info()

    def create_execution_file():
        cp = package.get().strip()
        py_file = selected_file["name"]
        if not cp or not version.get().strip() or not py_file:
            messagebox.showwarning(
                title="Debian App Builder",
                message="Package, version, and a target file are required.",
            )
            return
        bin_path = c.write_bin_file(package_root, cp, py_file)
        if bin_path:
            file_state["execution_created"] = True
            log(f"Created launcher at {bin_path}.", "ok")
        update_action_states()
        update_package_info()

    def create_desktop_file():
        cp = package.get().strip()
        entry_name = desktop_name.get().strip()
        entry_exec = desktop_exec.get().strip()
        if not cp or not entry_name or not entry_exec:
            messagebox.showwarning(
                title="Debian App Builder",
                message="Package, desktop name, and Exec are required.",
            )
            return
        desktop_path = c.write_desktop_file(
            package_root, cp, entry_name, entry_exec,
            comment=desktop_comment.get().strip(),
            categories=desktop_categories.get().strip() or "Utility",
            icon=desktop_icon.get().strip(),
            terminal=desktop_term.get().strip(),
        )
        if desktop_path:
            file_state["desktop_created"] = True
            log(f"Created {Path(desktop_path).name}.", "ok")
            messagebox.showinfo("Debian App Builder", f"Successfully created {Path(desktop_path).name}.")
            update_package_info()

    def build_package():
        cp = package.get().strip()
        cv = version.get().strip()
        if not cp or not cv or not selected_file["name"]:
            messagebox.showwarning(
                title="Debian App Builder",
                message="Package, version, and a target file are required.",
            )
            return
        if not build_command:
            log(f"Cannot build on this system: {build_system}.", "error")
            set_status(f"Build unavailable: {build_system}", ok=False)
            return
        start_busy()
        set_status("Building package...", ok=None)
        log(f"Building Debian package on {build_system}...")
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
                    archive_path = package_path.parent / f"{package_path.name}.deb"
                    linux_archive = f"/mnt/{drive}/" + "/".join(archive_path.parts[1:])
                    command_prefix = [build_command]
                else:
                    parts = package_path.parts
                    drive = parts[2] if len(parts) > 2 and parts[1] == "mnt" else ""
                    linux_root = str(package_path)
                    linux_archive = str(package_path.parent / f"{package_path.name}.deb")
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
                    [build_command, "--build", str(package_path)],
                    capture_output=True, text=True)
        except (OSError, subprocess.SubprocessError) as error:
            end_busy()
            log(f"Build failed: {error}", "error")
            set_status("Build failed", ok=False)
            return
        if result.returncode != 0:
            end_busy()
            log(result.stderr.strip() or "dpkg-deb could not build the package.", "error")
            set_status("Build failed", ok=False)
            return
        end_busy()
        log(result.stdout.strip() or "Package built successfully.", "ok")
        set_status("Build successful", ok=True)

    def set_write_inputs_state(state):
        for widget in (
            package, version, architecture, depends, maintainer, description,
            desktop_name, desktop_comment, desktop_exec, desktop_categories,
            desktop_icon, desktop_icon_button,
        ):
            widget.configure(state=state)

    build_ready_announced = {"value": False}

    def desktop_form_ready():
        return bool(package.get().strip() and desktop_name.get().strip() and desktop_exec.get().strip())

    def update_action_states(*_event):
        control_ready = all((package.get().strip(), version.get().strip(),
                             maintainer.get().strip(), description.get().strip()))
        execution_ready = bool(package.get().strip() and version.get().strip() and selected_file["name"])
        desktop_ready = desktop_form_ready()
        build_ready = bool(file_state["control_created"] and file_state["execution_created"]
                          and file_state["desktop_created"] and build_command)
        ctrl_btn.configure(state="normal" if control_ready else "disabled")
        make_exec.configure(state="normal" if execution_ready else "disabled")
        desktop_btn.configure(state="normal" if desktop_ready else "disabled")
        build_btn.configure(state="normal" if build_ready else "disabled")
        if build_ready and not build_ready_announced["value"]:
            log("Everything is ready. Press BUILD when you're done.", "ok")
        build_ready_announced["value"] = build_ready
        if not build_command:
            set_status(f"Build unavailable: {build_system}", ok=False)
        elif build_ready:
            set_status("Ready to build", ok=True)
        else:
            set_status("Complete the required steps", ok=None)

    for entry in (package, version, maintainer, description, desktop_name, desktop_exec):
        entry.bind("<KeyRelease>", update_action_states)

    set_write_inputs_state("normal" if selected_file["name"] else "disabled")
    update_action_states()
    update_package_info()
    refresh_file_indicator()
    if not build_command:
        log(f"Build disabled: {build_system}.", "error")
    app.mainloop()



def build_structure():
    package_name = output.get().strip()
    version = output2.get().strip()

    if not package_name or not version:
        messagebox.showwarning(
            title="Debian App Builder",
            message="Package name and version are required.",
        )
        return

    package_root = create_deb_structure(package_name, version, arch="amd64")
    root.destroy()
    writefiles(package_root, package_name, version)


def askPyfile(package_root, package_name):
    return c.choose_and_copy(f"{package_root}/usr/share/{package_name}/")


ctk.set_appearance_mode("system")
root = ctk.CTk()

center_window(root, 420, 470)
root.resizable(False, False)
root.title("Debian App Builder")
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
output2.grid(row=3, column=0, padx=16, pady=(0, 16), sticky="ew")

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
root.mainloop()
