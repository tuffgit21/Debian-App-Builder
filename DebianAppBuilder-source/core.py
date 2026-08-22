import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import stat
from tkinter import filedialog, messagebox
import sysconfig
DEFAULT_ICON_NAME = "DebAppBuilderIcon.png"
# Packages to vendor into the deb package tree
PACKAGES_TO_VENDOR = ["customtkinter", "packaging", "darkdetect"]


def vendor_dependencies(package_root: str, package_name: str) -> str:
    """
    Spawns an isolated background process to install dependencies and 
    vendor them without running into Windows file locks from the active GUI.
    """
    vendor_dir = os.path.abspath(os.path.join(package_root, "usr", "share", package_name, "vendor"))
    os.makedirs(vendor_dir, exist_ok=True)

    # Inline script executed in a completely separate Python process
    worker_script = f"""
import os, sys, shutil, tempfile, subprocess, stat

PACKAGES = {PACKAGES_TO_VENDOR!r}
vendor_dir = r"{vendor_dir}"

def remove_readonly(func, path, exc_info):
    os.chmod(path, stat.S_IWRITE)
    func(path)

with tempfile.TemporaryDirectory() as tmp_venv:
    # 1. Create isolated build venv
    subprocess.check_call([sys.executable, "-m", "venv", tmp_venv])
    
    venv_python = os.path.join(tmp_venv, "Scripts", "python.exe") if os.name == "nt" else os.path.join(tmp_venv, "bin", "python3")
    
    # 2. Install target packages
    subprocess.check_call([venv_python, "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_call([venv_python, "-m", "pip", "install"] + PACKAGES)
    
    # 3. Locate site-packages
    if os.name == "nt":
        site_packages = os.path.join(tmp_venv, "Lib", "site-packages")
    else:
        lib_dir = os.path.join(tmp_venv, "lib")
        site_packages = [os.path.join(lib_dir, d, "site-packages") for d in os.listdir(lib_dir) if os.path.isdir(os.path.join(lib_dir, d))][0]

    ignored = {{"__pycache__", "pip", "pkg_resources", "setuptools", "_distutils_hack"}}

    # 4. Copy files safely
    for item in os.listdir(site_packages):
        if item in ignored or item.endswith(".pth"):
            continue
        src = os.path.join(site_packages, item)
        dest = os.path.join(vendor_dir, item)
        
        if os.path.isdir(src):
            shutil.copytree(src, dest, dirs_exist_ok=True, symlinks=False)
        else:
            if os.path.exists(dest):
                try:
                    os.remove(dest)
                except PermissionError:
                    os.chmod(dest, stat.S_IWRITE)
                    os.remove(dest)
            shutil.copy2(src, dest)
"""

    try:
        # Run the vendoring routine in a completely detached Python process
        result = subprocess.run(
            [sys.executable, "-c", worker_script],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Unknown error in sub-process.")

        messagebox.showinfo("Debian App Builder", f"Successfully vendored dependencies into:\n{vendor_dir}")
        return vendor_dir

    except Exception as e:
        messagebox.showerror("Debian App Builder", f"Failed to vendor dependencies:\n{e}")
        return ""


def _find_site_packages(venv_dir: str) -> str:
    """Locate the site-packages folder inside a venv cross-platform."""
    # Calculates the site-packages directory relative to the virtualenv prefix
    site_packages = sysconfig.get_path("purelib", vars={"base": venv_dir, "platbase": venv_dir})
    
    if os.path.exists(site_packages):
        return site_packages
        
    raise FileNotFoundError(f"Could not find site-packages under {venv_dir}")


def choose_and_copy(destination_dir):
    """
    Prompts user to select a File (Python, C, Image) OR a Folder.
    Compiles .c files into executable binaries automatically via gcc.
    """
    choice = messagebox.askyesno(
        "Select Type", 
        "Click YES to select a File (.py, .c, .png)\nClick NO to select a Folder/Directory"
    )

    if choice:  # File path
        file_path = filedialog.askopenfilename(
            title="Select Python, C, or PNG file",
            filetypes=[
                ("Supported files", "*.py *.c *.png"),
                ("Python files", "*.py"),
                ("C source files", "*.c"),
                ("PNG images", "*.png"),
                ("All files", "*.*"),
            ],
        )
        if file_path:
            os.makedirs(destination_dir, exist_ok=True)
            filename = os.path.basename(file_path)

            # Compile C files directly to target binary name
            if filename.endswith(".c"):
                output_bin = os.path.splitext(filename)[0]
                dest_path = os.path.join(destination_dir, output_bin)
                try:
                    subprocess.check_call(["gcc", file_path, "-o", dest_path])
                    messagebox.showinfo("Debian App Builder", f"Compiled {filename} -> {dest_path}")
                    return output_bin
                except Exception as e:
                    messagebox.showerror("Debian App Builder", f"Failed to compile C file with gcc: {e}")
                    return None
            else:
                dest_path = os.path.join(destination_dir, filename)
                shutil.copy2(file_path, dest_path)
                messagebox.showinfo("Debian App Builder", f"Successfully copied file to {dest_path}")
                return filename
    else:  # Folder path
        dir_path = filedialog.askdirectory(title="Select Folder to Copy")
        if dir_path:
            os.makedirs(destination_dir, exist_ok=True)
            folder_name = os.path.basename(dir_path.rstrip("/\\"))
            dest_path = os.path.join(destination_dir, folder_name)

            if os.path.exists(dest_path):
                shutil.rmtree(dest_path)
            shutil.copytree(dir_path, dest_path)
            messagebox.showinfo("Debian App Builder", f"Successfully copied directory to {dest_path}")
            return folder_name

    return None


def create_deb_structure(package_name, version, arch="amd64"):
    root = f"{package_name}_{version}_{arch}"
    updating = os.path.isdir(root)

    dirs = [
        f"{root}/DEBIAN",
        f"{root}/usr/bin",
        f"{root}/usr/share/applications",
        f"{root}/usr/share/{package_name}",
    ]

    for d in dirs:
        os.makedirs(d, exist_ok=True)
    file_path = os.path.dirname(os.path.abspath(root))
    if updating:
        messagebox.showinfo(
            "Debian App Builder",
            f"You are now updating this structure: '{root}' in {file_path}",
        )
    else:
        messagebox.showinfo(
            "Debian App Builder",
            f"Successfully created the '{root}' deb structure in {file_path}",
        )
    return root


def write_control_file(root, package_name, version, maintainer, description, arch="amd64", depends=""):
    control_path = f"{root}/DEBIAN/control"
    with open(control_path, "w") as f:
        f.write(f"Package: {package_name}\n")
        f.write(f"Version: {version}\n")
        f.write(f"Architecture: {arch}\n")
        if depends:
            f.write(f"Depends: {depends}\n")
        f.write(f"Maintainer: {maintainer}\n")
        f.write(f"Description: {description}\n")


def write_bin_file(package_root, package_name, py_file):
    try:
        bin_path = os.path.join(package_root, "usr", "bin", package_name)
        os.makedirs(os.path.dirname(bin_path), exist_ok=True)
        target_path = f"/usr/share/{package_name}/{py_file}"
        vendor_path = f"/usr/share/{package_name}/vendor"

        with open(bin_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("#!/bin/sh\n")
            if py_file.endswith(".py"):
                # Export vendor folder path into PYTHONPATH
                f.write(f'export PYTHONPATH="{vendor_path}:$PYTHONPATH"\n')
                f.write(f'exec python3 {shlex.quote(target_path)} "$@"\n')
            else:
                # Direct binary launcher for C executables
                f.write(f'exec {shlex.quote(target_path)} "$@"\n')

        os.chmod(bin_path, 0o755)
        messagebox.showinfo("Debian App Builder", "Successfully created the launcher!")
        return bin_path
    except OSError as error:
        messagebox.showerror(
            "Debian App Builder",
            f"Error while creating the launcher file: {error}",
        )
        return None


def write_desktop_file(
    package_root,
    package_name,
    name,
    exec_command,
    terminal="true",
    comment="",
    categories="Utility",
    icon="",
):
    term_str = str(terminal).strip().lower() if terminal is not None else ""

    if term_str == "":
        messagebox.showerror(
            title="Debian App Builder",
            message="ERROR!\nThe terminal field cannot be empty!",
        )
        return None
    elif term_str not in ("true", "false"):
        messagebox.showwarning(
            title="Debian App Builder",
            message="WARNING!\nTo show the terminal or no.\nType true or false.",
        )
        return None

    app_share_dir = os.path.join(package_root, "usr", "share", package_name)
    os.makedirs(app_share_dir, exist_ok=True)
    
    default_icon_dest = os.path.join(app_share_dir, DEFAULT_ICON_NAME)
    icon_input = icon.strip()

    try:
        # Case 1: Custom file path provided by user
        if icon_input and os.path.isfile(icon_input):
            custom_filename = os.path.basename(icon_input)
            dest_icon_path = os.path.join(app_share_dir, custom_filename)

            # Copy custom icon into package directory
            shutil.copy2(icon_input, dest_icon_path)

            # Remove default icon if it's no longer being used
            if custom_filename != DEFAULT_ICON_NAME and os.path.exists(default_icon_dest):
                os.remove(default_icon_dest)

            final_icon_value = custom_filename

        # Case 2: User specified default icon or left field empty
        else:
            icon_source = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "__pycache__",
                DEFAULT_ICON_NAME,
            )
            if os.path.isfile(icon_source):
                shutil.copyfile(icon_source, default_icon_dest)
            
            final_icon_value = DEFAULT_ICON_NAME

        # Write .desktop entry
        desktop_path = os.path.join(
            package_root,
            "usr",
            "share",
            "applications",
            f"{package_name}.desktop",
        )
        os.makedirs(os.path.dirname(desktop_path), exist_ok=True)

        with open(desktop_path, "w", encoding="utf-8", newline="\n") as desktop_file:
            desktop_file.write("[Desktop Entry]\n")
            desktop_file.write("Version=1.0\n")
            desktop_file.write("Type=Application\n")
            desktop_file.write(f"Name={name}\n")
            desktop_file.write(f"Exec={exec_command}\n")
            desktop_file.write(f"Terminal={term_str}\n")
            if comment.strip():
                desktop_file.write(f"Comment={comment.strip()}\n")
            if categories.strip():
                desktop_file.write(f"Categories={categories.strip()}\n")
            desktop_file.write(f"Icon=/usr/share/{package_name}/{final_icon_value}\n")

        return desktop_path

    except OSError as error:
        messagebox.showerror(
            "Debian App Builder",
            f"Error while creating the desktop file: {error}",
        )
        return None