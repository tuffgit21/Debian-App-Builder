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

ICON_PATH = Path(__file__).with_name("__pycache__") / "DebAppBuilderIcon.png"
if platform.system() == "Windows":
    WINDOW_ICON_PATH = ICON_PATH.with_suffix(".ico")
print('''THIS PROJECT IS OPEN-SOURCE, YOU CAN MODIFY, DISTRIBUTE AND USE IT FREELY.\nHowever you must credit the original author and the project repository if you use it in your own project.\nSincerely Tuffgit21 site:https://tuffgit21.github.io/\nGithub repository:https://github.com/tuffgit21/Debian-App-Builder/ 
    ''')

def get_build_environment():
    system = platform.system()

    if system == "Windows":
        wsl_path = shutil.which("wsl.exe") or shutil.which("wsl")
        if wsl_path:
            return "wsl", wsl_path, "Windows (WSL)"
        return None, None, "Windows (WSL is not available)"

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
    icon = tk.PhotoImage(file=ICON_PATH)
    if platform.system() == "Windows":
        window.iconbitmap(default=str(WINDOW_ICON_PATH))
    else:
        window.iconphoto(True, icon)
    window.window_icon = icon
    return icon.subsample(15, 15)

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
    center_window(app,420,650)
    app.title("Debian App Builder (WRITE_MODE)")
    app.resizable(False, False)
    window_icon = load_window_icon(app)

    header = ctk.CTkFrame(app, fg_color="transparent")
    header.pack(fill="x", padx=24, pady=(20, 2))
    title_row = ctk.CTkFrame(header, fg_color="transparent")
    title_row.pack()
    ctk.CTkLabel(title_row, image=window_icon, text="").pack(side="left", padx=(0, 8))
    label2 = ctk.CTkLabel(
        title_row,
        text="Debian App Builder",
        font=ctk.CTkFont(size=22, weight="bold"),
    )
    label2.pack(side="left")
    label3 = ctk.CTkLabel(header, text="WRITE MODE")
    label3.pack(pady=(4, 0))

    scroll_frame = ctk.CTkScrollableFrame(app, fg_color="transparent")
    scroll_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    file_frame = ctk.CTkFrame(scroll_frame)
    file_frame.pack(fill="x", padx=12, pady=8)
    ctk.CTkLabel(file_frame, text="Application Target File or Folder", anchor="w").pack(
        fill="x", padx=16, pady=(12, 4)
    )
    application_path = Path(package_root) / "usr" / "share" / package_name
    existing_files = sorted(path for path in application_path.iterdir() if path.name != "vendor" and path.name != "DebAppBuilderIcon.png") if application_path.exists() else []
    selected_file = {"name": existing_files[0].name if existing_files else None}

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

    select_button = ctk.CTkButton(
        file_frame,
        text="Choose File or Folder",
        command=choose_python_file,
    )
    select_button.pack(fill="x", padx=16, pady=(4, 6))

    vendor_button = ctk.CTkButton(
        file_frame,
        text="Vendor Dependencies (pip3) - Optional",
        command=vendor_pkgs,
        fg_color="#1f538d",
    )
    vendor_button.pack(fill="x", padx=16, pady=(0, 14))

    file_list_frame = ctk.CTkFrame(file_frame, fg_color="transparent")
    file_list_frame.pack(fill="x", padx=16, pady=(0, 12))

    info_frame = ctk.CTkFrame(scroll_frame)
    info_frame.pack(fill="x", padx=12, pady=8)
    info_frame.grid_columnconfigure(1, weight=1)
    info_values = {
        "location": ctk.StringVar(value=str(Path(package_root).resolve())),
        "files": ctk.StringVar(),
        "directories": ctk.StringVar(),
        "application": ctk.StringVar(value="Not selected"),
    }

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

    def refresh_file_indicator():
        for child in file_list_frame.winfo_children():
            child.destroy()

        application_path = Path(package_root) / "usr" / "share" / package_name
        files = sorted(path for path in application_path.iterdir() if path.name != "vendor" and path.name != "DebAppBuilderIcon.png") if application_path.exists() else []
        if not files:
            ctk.CTkLabel(
                file_list_frame,
                text="No application files selected",
                text_color="gray",
            ).pack(anchor="w")
            return

        for file_path in files:
            file_row = ctk.CTkFrame(file_list_frame, fg_color="transparent")
            file_row.pack(fill="x", pady=2)
            ctk.CTkLabel(file_row, text=file_path.name, anchor="w").pack(
                side="left", fill="x", expand=True
            )
            size_str = "Folder" if file_path.is_dir() else format_file_size(file_path.stat().st_size)
            ctk.CTkLabel(
                file_row,
                text=size_str,
                width=70,
            ).pack(side="left", padx=6)
            ctk.CTkButton(
                file_row,
                text="X",
                width=28,
                height=24,
                command=lambda path=file_path: remove_application_file(path),
            ).pack(side="right")

    def add_info_row(row, label, variable):
        ctk.CTkLabel(info_frame, text=label, anchor="w").grid(
            row=row, column=0, padx=(16, 10), pady=5, sticky="w"
        )
        ctk.CTkLabel(info_frame, textvariable=variable, anchor="w").grid(
            row=row, column=1, padx=(0, 16), pady=5, sticky="ew"
        )

    add_info_row(0, "Location:", info_values["location"])
    add_info_row(1, "Files:", info_values["files"])
    add_info_row(2, "Directories:", info_values["directories"])
    add_info_row(3, "Application:", info_values["application"])
    file_state = {
        "control_created": (Path(package_root) / "DEBIAN" / "control").is_file(),
        "execution_created": (Path(package_root) / "usr" / "bin" / package_name).is_file(),
        "desktop_created": (
            Path(package_root)
            / "usr"
            / "share"
            / "applications"
            / f"{package_name}.desktop"
        ).is_file(),
    }

    metadata_frame = ctk.CTkFrame(scroll_frame)
    metadata_frame.pack(fill="x", padx=12, pady=8)
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

    desktop_frame = ctk.CTkFrame(scroll_frame)
    desktop_frame.pack(fill="x", padx=12, pady=8)
    desktop_frame.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(
        desktop_frame,
        text=f"Desktop entry: {package_name}.desktop",
        anchor="w",
    ).grid(row=0, column=0, columnspan=2, padx=16, pady=(16, 8), sticky="w")

    desktop_name_label = ctk.CTkLabel(desktop_frame, text="Name:", anchor="w")
    desktop_name_label.grid(row=1, column=0, padx=(16, 10), pady=6, sticky="w")
    desktop_name = ctk.CTkEntry(desktop_frame)
    desktop_name.insert(0, package_name)
    desktop_name.grid(row=1, column=1, padx=(0, 16), pady=6, sticky="ew")

    desktop_comment_label = ctk.CTkLabel(desktop_frame, text="Comment:", anchor="w")
    desktop_comment_label.grid(row=2, column=0, padx=(16, 10), pady=6, sticky="w")
    desktop_comment = ctk.CTkEntry(desktop_frame)
    desktop_comment.grid(row=2, column=1, padx=(0, 16), pady=6, sticky="ew")

    desktop_exec_label = ctk.CTkLabel(desktop_frame, text="Exec:", anchor="w")
    desktop_exec_label.grid(row=3, column=0, padx=(16, 10), pady=6, sticky="w")
    desktop_exec = ctk.CTkEntry(desktop_frame)
    desktop_exec.insert(0, package_name)
    desktop_exec.grid(row=3, column=1, padx=(0, 16), pady=6, sticky="ew")
    
    desktop_term_label = ctk.CTkLabel(desktop_frame, text="Terminal:", anchor="w")
    desktop_term_label.grid(row=3, column=0, padx=(16, 10), pady=6, sticky="w")
    desktop_term = ctk.CTkEntry(desktop_frame)
    desktop_term.insert(0,"true")
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

    def choose_desktop_icon():
        icon_path = filedialog.askopenfilename(
            title="Select desktop icon",
            filetypes=[("Image files", "*.png *.ico *.xpm"), ("All files", "*.*")],
        )
        if icon_path:
            desktop_icon.delete(0, "end")
            desktop_icon.insert(0, icon_path)
            update_action_states()

    desktop_icon_button = ctk.CTkButton(
        desktop_icon_frame,
        text="Browse",
        width=78,
        command=choose_desktop_icon,
    )
    desktop_icon_button.grid(row=0, column=1, padx=(8, 0))

    def create_control_file():
        control_package = package.get().strip()
        control_version = version.get().strip()
        control_maintainer = maintainer.get().strip()
        control_description = description.get().strip()

        if not control_package or not control_version or not control_maintainer or not control_description:
            messagebox.showwarning(
                title="Debian App Builder",
                message="Package, version, maintainer, and description are required.",
            )
            return

        try:
            c.write_control_file(
                package_root,
                control_package,
                control_version,
                control_maintainer,
                control_description,
                arch=architecture.get().strip() or "amd64",
                depends=depends.get().strip(),
            )
        except OSError as error:
            messagebox.showerror("Debian App Builder", f"Could not create control file: {error}")
            return

        messagebox.showinfo("Debian App Builder", "Successfully created DEBIAN/control.")
        file_state["control_created"] = True
        update_action_states()
        update_package_info()

    action_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
    action_frame.pack(fill="x", padx=12, pady=(12, 20))
    ctrl_btn = ctk.CTkButton(action_frame, text="Create Control file", command=create_control_file)
    ctrl_btn.pack(fill="x", pady=(0, 8))

    def create_execution_file():
        control_package = package.get().strip()
        py_file = selected_file["name"]

        if not control_package or not version.get().strip() or not py_file:
            messagebox.showwarning(
                title="Debian App Builder",
                message="Package, version, and a target file are required.",
            )
            return

        bin_path = c.write_bin_file(package_root, control_package, py_file)
        if bin_path:
            file_state["execution_created"] = True
        update_action_states()
        update_package_info()

    def create_desktop_file():
        control_package = package.get().strip()
        entry_name = desktop_name.get().strip()
        entry_exec = desktop_exec.get().strip()

        if not control_package or not entry_name or not entry_exec:
            messagebox.showwarning(
                title="Debian App Builder",
                message="Package, desktop name, terminal and Exec are required.",
            )
            return

        desktop_path = c.write_desktop_file(
            package_root,
            control_package,
            entry_name,
            entry_exec,
            comment=desktop_comment.get().strip(),
            categories=desktop_categories.get().strip() or "Utility",
            icon=desktop_icon.get().strip(),
            terminal=desktop_term.get().strip(),
        )
        if desktop_path:
            file_state["desktop_created"] = True
            messagebox.showinfo(
                "Debian App Builder",
                f"Successfully created {Path(desktop_path).name}.",
            )
            update_package_info()

    def build_package():
        control_package = package.get().strip()
        control_version = version.get().strip()

        if not control_package or not control_version or not selected_file["name"]:
            messagebox.showwarning(
                title="Debian App Builder",
                message="Package, version, and a target file are required.",
            )
            return

        if not build_command:
            messagebox.showerror(
                "Debian App Builder",
                f"Cannot build on this system: {build_system}.",
            )
            return

        try:
            package_path = Path(package_root).resolve()
            stage_on_linux = build_mode == "wsl" or (
                platform.system() == "Linux" and len(package_path.parts) > 1 and package_path.parts[1] == "mnt"
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
                    linux_root = str(package_path)
                    linux_archive = f"/mnt/{drive}/" + "/".join(package_path.parts[1:]) + ".deb"
                    command_prefix = []

                wsl_root = f"/tmp/debian-app-builder-{package_path.name}"
                subprocess.run(
                    command_prefix + ["rm", "-rf", wsl_root],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                subprocess.run(
                    command_prefix + ["cp", "-a", linux_root, wsl_root],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                permission_targets = (
                    (f"{wsl_root}/DEBIAN", "755"),
                    (f"{wsl_root}/DEBIAN/control", "644"),
                    (f"{wsl_root}/usr/bin/{control_package}", "755"),
                )
                for target, mode in permission_targets:
                    subprocess.run(
                        command_prefix + ["chmod", mode, target],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                result = subprocess.run(
                    command_prefix + ["dpkg-deb", "--build", wsl_root, linux_archive],
                    capture_output=True,
                    text=True,
                )
                subprocess.run(
                    command_prefix + ["rm", "-rf", wsl_root],
                    capture_output=True,
                    text=True,
                    check=True,
                )
            else:
                result = subprocess.run(
                    [build_command, "--build", str(package_path)],
                    capture_output=True,
                    text=True,
                )
        except (OSError, subprocess.SubprocessError) as error:
            messagebox.showerror("Debian App Builder", f"Could not build package: {error}")
            return

        if result.returncode != 0:
            messagebox.showerror(
                "Debian App Builder",
                result.stderr.strip() or "dpkg-deb could not build the package.",
            )
            return

        messagebox.showinfo(
            "Debian App Builder",
            f"Successfully built the Debian package on {build_system}.\n{result.stdout.strip()}",
        )

    make_exec = ctk.CTkButton(
        action_frame,
        text="Create Execution file",
        command=create_execution_file,
    )
    make_exec.pack(fill="x")
    desktop_btn = ctk.CTkButton(
        action_frame,
        text=f"Create {package_name}.desktop file",
        command=create_desktop_file,
        state="disabled",
    )
    desktop_btn.pack(fill="x", pady=(8, 0))
    build_btn = ctk.CTkButton(
        action_frame,
        text="⚠️BUILD⚠️",
        command=build_package,
        fg_color="red",
        text_color="black",
        hover_color="#cc0000",
    )
    build_btn.pack(fill="x", pady=(8, 0))

    def set_write_inputs_state(state):
        for widget in (
            package,
            version,
            architecture,
            depends,
            maintainer,
            description,
            desktop_name,
            desktop_comment,
            desktop_exec,
            desktop_categories,
            desktop_icon,
            desktop_icon_button,
        ):
            widget.configure(state=state)

    build_ready_announced = {"value": False}

    def desktop_form_ready():
        return bool(
            package.get().strip()
            and desktop_name.get().strip()
            and desktop_exec.get().strip()
        )

    def update_action_states(*_event):
        control_ready = all(
            (
                package.get().strip(),
                version.get().strip(),
                maintainer.get().strip(),
                description.get().strip(),
            )
        )
        execution_ready = bool(package.get().strip() and version.get().strip() and selected_file["name"])
        desktop_ready = desktop_form_ready()
        build_ready = bool(
            file_state["control_created"]
            and file_state["execution_created"]
            and file_state["desktop_created"]
            and build_command
        )
        ctrl_btn.configure(state="normal" if control_ready else "disabled")
        make_exec.configure(state="normal" if execution_ready else "disabled")
        desktop_btn.configure(state="normal" if desktop_ready else "disabled")
        build_btn.configure(state="normal" if build_ready else "disabled")

        if build_ready and not build_ready_announced["value"]:
            messagebox.showinfo("Debian App Builder", "Everything is ready. The Build button is now usable.")
        build_ready_announced["value"] = build_ready

    for entry in (
        package,
        version,
        maintainer,
        description,
        desktop_name,
        desktop_exec,
    ):
        entry.bind("<KeyRelease>", update_action_states)

    set_write_inputs_state("normal" if selected_file["name"] else "disabled")
    update_action_states()
    update_package_info()
    refresh_file_indicator()
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

center_window(root,380,400)
root.resizable(False, False)
root.title("Debian App Builder")
window_icon = load_window_icon(root)

header = ctk.CTkFrame(root, fg_color="transparent")
header.pack(fill="x", padx=24, pady=(28, 16))
title_row = ctk.CTkFrame(header, fg_color="transparent")
title_row.pack()
ctk.CTkLabel(title_row, image=window_icon, text="").pack(side="left", padx=(0, 8))
label1 = ctk.CTkLabel(
    title_row,
    text="Debian App Builder",
    font=ctk.CTkFont(size=22, weight="bold"),
)
label1.pack(side="left")
ctk.CTkLabel(header, text="Create a Debian package structure").pack(pady=(4, 0))

input_frame = ctk.CTkFrame(root)
input_frame.pack(fill="x", padx=24, pady=8)
input_frame.grid_columnconfigure(0, weight=1)

out_label = ctk.CTkLabel(input_frame, text="Package name", anchor="w")
out_label.grid(row=0, column=0, padx=16, pady=(16, 4), sticky="w")
output = ctk.CTkEntry(input_frame, placeholder_text="example-app")
output.grid(row=1, column=0, padx=16, pady=(0, 10), sticky="ew")

out_label2 = ctk.CTkLabel(input_frame, text="Package version", anchor="w")
out_label2.grid(row=2, column=0, padx=16, pady=(4, 4), sticky="w")
output2 = ctk.CTkEntry(input_frame, placeholder_text="1.0.0")
output2.grid(row=3, column=0, padx=16, pady=(0, 16), sticky="ew")

Build_btn = ctk.CTkButton(
    root,
    text="Make the structure",
    command=build_structure,
    height=40,
)
Build_btn.pack(fill="x", padx=24, pady=(20, 24))
root.mainloop()
