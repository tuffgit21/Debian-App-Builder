import os
import re
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
vendor_dir = {vendor_dir!r}

def remove_readonly(func, path, exc_info):
    os.chmod(path, stat.S_IWRITE)
    func(path)

def cleanup_build_dir(path):
    shutil.rmtree(path, ignore_errors=True)
    if os.path.exists(path):
        try:
            shutil.rmtree(path, onerror=remove_readonly)
        except OSError:
            pass

tmp_venv = tempfile.mkdtemp(prefix="debappbuilder-vendor-")
try:
    # 1. Create isolated build venv
    subprocess.check_call([sys.executable, "-m", "venv", tmp_venv])
    
    venv_python = os.path.join(tmp_venv, "Scripts", "python.exe") if os.name == "nt" else os.path.join(tmp_venv, "bin", "python3")
    
    # 2. Install target packages
    subprocess.check_call([venv_python, "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_call([venv_python, "-m", "pip", "install"] + PACKAGES)
    
    # 3. Locate site-packages reliably via the venv's own interpreter
    listing = subprocess.check_output(
        [venv_python, "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
        text=True,
    )
    site_packages = listing.strip()

    ignored = {{"__pycache__", "pip", "pkg_resources", "setuptools", "_distutils_hack", "wheel"}}

    # 4. Reset the vendor directory so stale files from previous
    #    runs can never shadow the freshly installed versions
    for entry in os.listdir(vendor_dir):
        victim = os.path.join(vendor_dir, entry)
        if os.path.isdir(victim):
            shutil.rmtree(victim, ignore_errors=True)
            if os.path.exists(victim):
                try:
                    shutil.rmtree(victim, onerror=remove_readonly)
                except OSError:
                    pass
        else:
            try:
                os.remove(victim)
            except PermissionError:
                os.chmod(victim, stat.S_IWRITE)
                os.remove(victim)

    # 5. Copy files safely
    for item in os.listdir(site_packages):
        top_level = item.split("-")[0].lower()
        if top_level in ignored or item.endswith(".pth"):
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
finally:
    # 6. Clean up the build venv without letting lock/read-only errors
    #    mask an otherwise successful vendoring run
    cleanup_build_dir(tmp_venv)
"""

    if getattr(sys, "frozen", False):
        python_exe = shutil.which("python") or shutil.which("python3")
    else:
        python_exe = sys.executable

    if not python_exe:
        messagebox.showerror(
            "Debian App Builder",
            "Vendoring dependencies requires a Python interpreter (python or python3) "
            "to be available on your PATH.\nIt cannot run from the bundled executable alone.",
        )
        return ""

    try:
        # Run the vendoring routine in a separate Python process so the active
        # GUI is never re-launched (sys.executable is the .exe when frozen).
        result = subprocess.run(
            [python_exe, "-c", worker_script],
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
        "Click YES to select a File (.py, .c)\nClick NO to select a Folder/Directory"
    )

    if choice:  # File path
        file_path = filedialog.askopenfilename(
            title="Select Python or C source file",
            filetypes=[
                ("Supported files", "*.py *.c"),
                ("Python files", "*.py"),
                ("C source files", "*.c"),
                ("All files", "*.*"),
            ],
        )
        if file_path:
            os.makedirs(destination_dir, exist_ok=True)
            filename = os.path.basename(file_path)

            # Compile C files directly to target binary name
            if filename.lower().endswith(".c"):
                output_bin = os.path.splitext(filename)[0]
                dest_path = os.path.join(destination_dir, output_bin)
                try:
                    subprocess.check_call(["gcc", file_path, "-o", dest_path])
                    # gcc on Windows may create dest_path + ".exe" even when -o without .exe
                    actual_path = dest_path
                    if not os.path.isfile(actual_path) and os.path.isfile(actual_path + ".exe"):
                        actual_path = actual_path + ".exe"
                    # ensure executable bit for Debian packaging
                    try:
                        if os.path.isfile(actual_path):
                            os.chmod(actual_path, 0o755)
                    except OSError:
                        pass
                    actual_name = os.path.basename(actual_path)
                    # For Debian the binary inside /usr/share/<pkg> should be without .exe;
                    # if we got a .exe, rename to without .exe for Linux compatibility
                    # but keep .exe handling robust – launcher will detect either
                    if actual_name.lower().endswith(".exe"):
                        # keep the file as-is, but return the actual name (with .exe)
                        # write_bin_file will handle .exe stripping/keeping correctly
                        messagebox.showinfo("Debian App Builder", f"Compiled {filename} -> {actual_path}")
                        return actual_name
                    messagebox.showinfo("Debian App Builder", f"Compiled {filename} -> {actual_path}")
                    return actual_name
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


def create_deb_structure(package_name, version, arch="amd64", output_dir=None):
    package_name = package_name.strip()
    version = version.strip()
    arch = arch.strip()

    if not package_name or not version or not arch:
        raise ValueError("Package name, version, and architecture are required.")
    if not re.fullmatch(r"[a-z0-9][a-z0-9+.-]*", package_name):
        raise ValueError(
            "Package name must use lowercase letters, numbers, '.', '+', or '-'."
        )
    if any(char in version or char in arch for char in ("/", "\\")):
        raise ValueError("Version and architecture cannot contain path separators.")

    # Prompt: "Choose where the .deb structure is created."
    if output_dir is None or str(output_dir).strip() == "":
        chosen = filedialog.askdirectory(title="Choose where the .deb structure is created.")
        if chosen:
            output_dir = chosen
        else:
            output_dir = os.getcwd()
    output_dir = os.path.abspath(str(output_dir).strip())
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    root = os.path.join(output_dir, f"{package_name}_{version}_{arch}")
    if os.path.exists(root) and not os.path.isdir(root):
        raise NotADirectoryError(f"A file already exists at the structure path: {root}")
    updating = os.path.isdir(root)

    dirs = [
        os.path.join(root, "DEBIAN"),
        os.path.join(root, "usr", "bin"),
        os.path.join(root, "usr", "share", "applications"),
        os.path.join(root, "usr", "share", package_name),
    ]

    for d in dirs:
        os.makedirs(d, exist_ok=True)
    file_path = os.path.dirname(root)
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


def choose_finished_deb_path(package_root, output_dir=None):
    """
    Prompt: "Choose where the finished .deb is saved."
    Returns the full .deb file path that should be used as the build output.
    If output_dir is a directory, the deb is placed inside it.
    If output_dir is a file path ending with .deb, that exact path is used.
    If output_dir is None/empty, prompts the user to choose a location.
    """
    pkg_name = os.path.basename(os.path.abspath(package_root.rstrip("/\\")))
    default_name = f"{pkg_name}.deb"
    # Prompt: "Choose where the finished .deb is saved."
    if output_dir is None or str(output_dir).strip() == "":
        # Prefer Save-As dialog so user can choose both location and filename
        try:
            chosen = filedialog.asksaveasfilename(
                title="Choose where the finished .deb is saved.",
                defaultextension=".deb",
                initialfile=default_name,
                initialdir=os.path.dirname(os.path.abspath(package_root)),
                filetypes=[("Debian package", "*.deb"), ("All files", "*.*")],
            )
        except Exception:
            chosen = None
        if chosen:
            return os.path.abspath(chosen)
        # Fallback to directory chooser if save dialog was cancelled/unsupported
        try:
            chosen_dir = filedialog.askdirectory(title="Choose where the finished .deb is saved.")
        except Exception:
            chosen_dir = None
        if chosen_dir:
            output_dir = chosen_dir
        else:
            output_dir = os.path.dirname(os.path.abspath(package_root))
    output_dir = str(output_dir).strip()
    if output_dir.lower().endswith(".deb"):
        out_dir = os.path.dirname(os.path.abspath(output_dir))
        if out_dir and not os.path.isdir(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        return os.path.abspath(output_dir)
    # treat as directory
    out_dir = os.path.abspath(output_dir)
    if not os.path.isdir(out_dir):
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError:
            pass
    return os.path.join(out_dir, default_name)


def validate_build_prerequisites(package_root, package_name):
    """
    Returns a list of missing prerequisites for BUILD.
    Checks on-disk existence, not just in-memory flags.
    Fixed: was requiring second control creation because payload check was too strict
           (checked only current package share) and control check was stale.
    """
    from pathlib import Path as _Path
    missing = []
    pkg = str(package_name).strip()
    root = _Path(str(package_root))
    if not pkg:
        missing.append("Package name is required")
        return missing
    # Control is package-agnostic – just check DEBIAN/control exists and is non-empty
    control_path = root / "DEBIAN" / "control"
    if not control_path.is_file() or control_path.stat().st_size == 0:
        missing.append("DEBIAN/control — Create Control file")
    if not (root / "usr" / "bin" / pkg).is_file():
        # fallback: check if bin file exists under original package dir name
        # (payload may have been copied before package rename)
        bin_alternates = list((root / "usr" / "bin").glob("*"))
        has_bin = any(b.is_file() for b in bin_alternates)
        if not has_bin:
            missing.append(f"usr/bin/{pkg} — Create Execution file")
        elif not (root / "usr" / "bin" / pkg).is_file():
            # bin exists but under different name – still report missing for current pkg
            missing.append(f"usr/bin/{pkg} — Create Execution file (found {bin_alternates[0].name if bin_alternates else 'none'}, expected {pkg})")
    if not (root / "usr" / "share" / "applications" / f"{pkg}.desktop").is_file():
        missing.append(f"usr/share/applications/{pkg}.desktop — Create Desktop file")
    # application payload: check both current pkg share and any share subfolder
    # (fixes double-control bug where payload was in original pkg folder after rename)
    has_payload = False
    candidates = [root / "usr" / "share" / pkg]
    # also scan all share subdirs if specific one empty (lenient)
    if not candidates[0].is_dir() or not any(p.name not in ("vendor", DEFAULT_ICON_NAME) for p in candidates[0].iterdir() if p.exists()):
        # check any payload in share
        share_root = root / "usr" / "share"
        if share_root.is_dir():
            for sub in share_root.iterdir():
                if sub.is_dir() and sub.name not in ("applications", "doc", "man", "icons", "pixmaps"):
                    for p in sub.iterdir():
                        if p.name not in ("vendor", DEFAULT_ICON_NAME):
                            has_payload = True
                            break
                elif sub.is_file() and sub.name not in ("vendor",):
                    has_payload = True
                if has_payload:
                    break
    else:
        has_payload = True
    # direct check for current pkg share
    app_share = root / "usr" / "share" / pkg
    if app_share.is_dir():
        for p in app_share.iterdir():
            if p.name not in ("vendor", DEFAULT_ICON_NAME):
                has_payload = True
                break
    if not has_payload:
        missing.append("Application file/folder — Choose File or Folder and ensure it is copied")
    return missing


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
        if not py_file or not str(py_file).strip():
            messagebox.showerror(
                "Debian App Builder",
                "No application file selected. Please choose a file/folder first.",
            )
            return None
        # Normalize – strip whitespace and directory components
        py_file = str(py_file).strip()
        # py_file may be a subpath like "myapp/main" when folder was selected;
        # keep as-is for target but ensure basename handling for .exe logic
        # For security, prevent absolute or traversal
        py_file = py_file.lstrip("/\\")
        # Resolve the actual file on disk inside the package share
        share_base = os.path.join(package_root, "usr", "share", package_name)
        candidate = os.path.join(share_base, py_file)
        # If candidate is a directory (folder selected), find the real executable inside
        if os.path.isdir(candidate):
            # look for executable: prefer file named like py_file, or first file
            found = None
            for entry in os.listdir(candidate):
                entry_path = os.path.join(candidate, entry)
                if os.path.isfile(entry_path):
                    # prefer non-.c/.png files
                    if entry.lower().endswith((".c", ".png")):
                        continue
                    found = entry
                    # prefer exact match or executable bit
                    if os.access(entry_path, os.X_OK):
                        break
            if found:
                py_file = f"{py_file}/{found}"
                candidate = os.path.join(share_base, py_file)
            else:
                messagebox.showerror(
                    "Debian App Builder",
                    f"Selected folder '{py_file}' contains no executable file.",
                )
                return None
        # Handle .exe suffix robustly – Debian binaries should be without .exe,
        # but Windows gcc may have produced a .exe. Launcher must point to the
        # actual filename that exists on disk, otherwise it would write only
        # "/usr/share/<pkg>" (if py_file empty) or wrong name.
        if not os.path.exists(candidate):
            # try alternate with / without .exe
            if py_file.lower().endswith(".exe"):
                alt = py_file[:-4]
            else:
                alt = py_file + ".exe"
            alt_candidate = os.path.join(share_base, alt)
            if os.path.exists(alt_candidate):
                py_file = alt
                candidate = alt_candidate
            else:
                # also try case where py_file is "myapp" but actual file is "myapp.exe" in same dir
                # already handled; if still missing, warn but continue – dpkg build will catch
                pass
        # Final guard: py_file must be a file name, not empty or just directory
        if not os.path.basename(py_file):
            messagebox.showerror(
                "Debian App Builder",
                f"Invalid application file '{py_file}'. Expected a file, not a directory.",
            )
            return None
        # Ensure py_file is quoted correctly and not just "/usr/share/<pkg>"
        if py_file.strip("/") == "" or py_file == package_name:
            # This would produce target "/usr/share/<pkg>/<pkg>" which is okay only if file named same as pkg
            # but avoid producing "/usr/share/<pkg>" alone
            pass
        bin_path = os.path.join(package_root, "usr", "bin", package_name)
        os.makedirs(os.path.dirname(bin_path), exist_ok=True)
        target_path = f"/usr/share/{package_name}/{py_file}"
        vendor_path = f"/usr/share/{package_name}/vendor"

        with open(bin_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("#!/bin/sh\n")
            # Normalize check for .py – strip .exe first
            check_name = py_file
            if check_name.lower().endswith(".exe"):
                check_name = check_name[:-4]
            if check_name.endswith(".py"):
                # Export vendor folder path into PYTHONPATH
                f.write(f'export PYTHONPATH="{vendor_path}:$PYTHONPATH"\n')
                f.write(f'exec python3 {shlex.quote(target_path)} "$@"\n')
            else:
                # Direct binary launcher for C executables (handles .exe if present)
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
    path="",
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
            source_dir = os.path.dirname(os.path.abspath(__file__))
            icon_source_candidates = [
                os.path.join(source_dir, DEFAULT_ICON_NAME),
                os.path.join(os.path.dirname(source_dir), "DebAppBuilderLogo.png"),
            ]
            icon_source = next(
                (p for p in icon_source_candidates if os.path.isfile(p)), None
            )
            if icon_source:
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
            # Path= working directory – support absolute path handling
            path_str = str(path).strip() if path is not None else ""
            if path_str:
                # Must be absolute per Desktop Entry Spec; reject relative to avoid broken launch
                if not path_str.startswith("/"):
                    messagebox.showwarning(
                        title="Debian App Builder",
                        message=f"WARNING!\nPath must be an absolute path (starting with '/'), got:\n{path_str}\n\nLeave empty for default or use e.g. /usr/share/{package_name}",
                    )
                    return None
                # Basic validation: no newline, not just '/'
                if "\n" in path_str or "\r" in path_str:
                    messagebox.showerror(
                        title="Debian App Builder",
                        message="ERROR!\nPath contains invalid characters.",
                    )
                    return None
                desktop_file.write(f"Path={path_str}\n")
            # Use hicolor theme name if hicolor icons were generated
            hicolor_base = os.path.join(package_root, "usr", "share", "icons", "hicolor")
            has_hicolor = False
            if os.path.isdir(hicolor_base):
                for sz in ["16x16", "32x32", "48x48", "64x64", "128x128", "256x256", "scalable"]:
                    exts = [".svg"] if sz == "scalable" else [".png"]
                    for ext in exts:
                        if os.path.isfile(os.path.join(hicolor_base, sz, "apps", f"{package_name}{ext}")):
                            has_hicolor = True
                            break
                    if has_hicolor:
                        break
            if has_hicolor:
                desktop_file.write(f"Icon={package_name}\n")
            else:
                desktop_file.write(f"Icon=/usr/share/{package_name}/{final_icon_value}\n")

        return desktop_path

    except OSError as error:
        messagebox.showerror(
            "Debian App Builder",
            f"Error while creating the desktop file: {error}",
        )
        return None


def generate_hicolor_icons(package_root, package_name, source_image_path, sizes=(16, 32, 48, 64, 128, 256)):
    """
    Automatically generate icons/hicolor folder structure.
    - sizes like 16x16, 32x32, 48x48, 64x64, 128x128, 256x256 as folders
    - scalable with .svg (if source is .svg put it in scalable/apps)
    Returns list of generated files or None on failure.
    """
    try:
        package_name = str(package_name).strip()
        if not package_name:
            messagebox.showerror("Debian App Builder", "Package name is required for hicolor icons.")
            return None
        source_image_path = str(source_image_path).strip()
        if not os.path.isfile(source_image_path):
            messagebox.showerror("Debian App Builder", f"Source image not found:\n{source_image_path}")
            return None

        ext = os.path.splitext(source_image_path)[1].lower()
        generated = []
        base_icon_name = f"{package_name}"

        if ext == ".svg":
            # scalable/apps/<package>.svg
            dest_dir = os.path.join(package_root, "usr", "share", "icons", "hicolor", "scalable", "apps")
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, base_icon_name + ".svg")
            shutil.copy2(source_image_path, dest_path)
            generated.append(dest_path)
            # Also optionally generate PNG sizes from SVG if cairosvg/Pillow available
            # For now just keep SVG in scalable; user can also provide PNG for other sizes
            try:
                from PIL import Image as _PILImage
                # Try to rasterize SVG via cairosvg if available for PNG sizes
                has_cairo = False
                try:
                    import cairosvg
                    has_cairo = True
                except ImportError:
                    has_cairo = False
                if has_cairo:
                    import tempfile
                    for sz in sizes:
                        dest_dir_png = os.path.join(package_root, "usr", "share", "icons", "hicolor", f"{sz}x{sz}", "apps")
                        os.makedirs(dest_dir_png, exist_ok=True)
                        dest_png = os.path.join(dest_dir_png, base_icon_name + ".png")
                        # use cairosvg to render at size
                        try:
                            cairosvg.svg2png(url=source_image_path, write_to=dest_png, output_width=sz, output_height=sz)
                            generated.append(dest_png)
                        except Exception:
                            continue
            except Exception:
                pass
            messagebox.showinfo("Debian App Builder", f"Hicolor scalable icon created:\n{dest_path}\n\nGenerated {len(generated)} file(s).")
            return generated
        else:
            # Raster image – generate each size via Pillow
            try:
                from PIL import Image
            except ImportError:
                messagebox.showerror("Debian App Builder", "Pillow is required to generate hicolor PNG icons.\nPlease install: pip install Pillow")
                return None
            try:
                src_img = Image.open(source_image_path).convert("RGBA")
            except Exception as e:
                messagebox.showerror("Debian App Builder", f"Failed to open source image:\n{e}")
                return None
            for sz in sizes:
                dest_dir = os.path.join(package_root, "usr", "share", "icons", "hicolor", f"{sz}x{sz}", "apps")
                os.makedirs(dest_dir, exist_ok=True)
                dest_path = os.path.join(dest_dir, base_icon_name + ".png")
                try:
                    # Use LANCZOS for high quality
                    resized = src_img.resize((sz, sz), Image.LANCZOS)
                    resized.save(dest_path, "PNG")
                    generated.append(dest_path)
                except Exception as e:
                    messagebox.showwarning("Debian App Builder", f"Failed to generate {sz}x{sz} icon:\n{e}")
                    continue
            # Also copy original to scalable if it's large enough? No, scalable only for SVG
            messagebox.showinfo("Debian App Builder", f"Hicolor icons generated for sizes: {', '.join(str(s)+'x'+str(s) for s in sizes)}\n\nIn: usr/share/icons/hicolor/\nGenerated {len(generated)} file(s).")
            return generated
    except Exception as e:
        messagebox.showerror("Debian App Builder", f"Failed to generate hicolor icons:\n{e}")
        return None


# ---------------------------------------------------------------------------
# AppStream metadata
# ---------------------------------------------------------------------------
def write_appstream_file(
    package_root,
    package_name,
    app_id="",
    name="",
    summary="",
    description="",
    developer_name="",
    project_license="GPL-3.0+",
    metadata_license="CC0-1.0",
    homepage_url="",
    categories="",
    keywords="",
    version="1.0",
):
    """
    Create AppStream metainfo file at:
        usr/share/metainfo/<app_id>.metainfo.xml

    This is the freedesktop.org AppStream spec used by GNOME Software /
    KDE Discover. Minimal required fields: <id>, <name>, <summary>,
    <metadata_license>, <project_license>.

    Returns the created file path on success, None on failure.
    """
    from xml.sax.saxutils import escape as _xml_escape
    import datetime

    try:
        package_name = str(package_name).strip()
        if not package_name:
            messagebox.showerror("Debian App Builder", "Package name is required for AppStream metadata.")
            return None

        app_id = str(app_id).strip() if app_id is not None else ""
        name = str(name).strip() if name is not None else ""
        summary = str(summary).strip() if summary is not None else ""
        description = str(description).strip() if description is not None else ""
        developer_name = str(developer_name).strip() if developer_name is not None else ""
        project_license = str(project_license).strip() or "GPL-3.0+"
        metadata_license = str(metadata_license).strip() or "CC0-1.0"
        homepage_url = str(homepage_url).strip() if homepage_url is not None else ""
        categories = str(categories).strip() if categories is not None else ""
        keywords = str(keywords).strip() if keywords is not None else ""
        version = str(version).strip() or "1.0"

        # --- Validation (mirrors write_control_file / write_desktop_file) ---
        if not name:
            messagebox.showerror("Debian App Builder", "AppStream: 'Name' field is required.")
            return None
        if not summary:
            messagebox.showerror("Debian App Builder", "AppStream: 'Summary' field is required.")
            return None
        if not description:
            messagebox.showerror("Debian App Builder", "AppStream: 'Description' field is required.")
            return None

        # Default app_id to reverse-DNS if not supplied – generic placeholder
        # (no longer hardcoded tuffgit21; caller may derive from Maintainer instead)
        if not app_id:
            # Generate a spec-compliant reverse-DNS id
            # Use package_name sanitized to [a-z0-9-] segments
            safe = re.sub(r"[^a-z0-9-]", "-", package_name.lower())
            safe = re.sub(r"-+", "-", safe).strip("-") or "app"
            app_id = f"com.example.{safe}"

        # AppStream id must contain at least one dot and not start with a dot
        if "." not in app_id:
            # keep simple package name as fallback but warn – still valid for metainfo filename
            pass

        # File name is <app_id>.metainfo.xml ( spec ) – fallback to package_name if app_id has path-unfriendly chars
        # Sanitize file name: keep alnum, dot, dash, underscore
        safe_filename = re.sub(r"[^A-Za-z0-9._-]", "-", app_id).strip("-.")
        if not safe_filename:
            safe_filename = package_name
        if not safe_filename.endswith(".metainfo.xml"):
            # if app_id already ends with .metainfo.xml keep, else add
            if safe_filename.lower().endswith(".metainfo.xml"):
                filename = safe_filename
            elif safe_filename.lower().endswith(".appdata.xml"):
                filename = safe_filename
            else:
                filename = f"{safe_filename}.metainfo.xml"

        metainfo_dir = os.path.join(package_root, "usr", "share", "metainfo")
        os.makedirs(metainfo_dir, exist_ok=True)
        dest_path = os.path.join(metainfo_dir, filename)

        # Escape XML values
        def esc(s):
            return _xml_escape(s, entities={"'": "&apos;", '"': "&quot;"})

        # Build categories list
        cat_list = [c.strip() for c in re.split(r"[;,]", categories) if c.strip()] if categories else []
        kw_list = [k.strip() for k in re.split(r"[,;]", keywords) if k.strip()] if keywords else []

        # Date for <release>
        today = datetime.date.today().isoformat()

        # Multi-paragraph description -> split on blank lines
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", description) if p.strip()]
        if not paragraphs:
            paragraphs = [description]

        lines = []
        lines.append('<?xml version="1.0" encoding="UTF-8"?>')
        lines.append('<component type="desktop-application">')
        lines.append(f'  <id>{esc(app_id)}</id>')
        lines.append(f'  <metadata_license>{esc(metadata_license)}</metadata_license>')
        lines.append(f'  <project_license>{esc(project_license)}</project_license>')
        lines.append(f'  <name>{esc(name)}</name>')
        lines.append(f'  <summary>{esc(summary)}</summary>')
        lines.append('  <description>')
        for para in paragraphs:
            # preserve single line breaks inside paragraph as spaces
            para_one_line = " ".join(para.splitlines()).strip()
            lines.append(f'    <p>{esc(para_one_line)}</p>')
        lines.append('  </description>')
        # launchable must match desktop file id
        lines.append(f'  <launchable type="desktop-id">{esc(package_name)}.desktop</launchable>')
        lines.append('  <provides>')
        lines.append(f'    <binary>{esc(package_name)}</binary>')
        lines.append('  </provides>')
        if homepage_url:
            lines.append(f'  <url type="homepage">{esc(homepage_url)}</url>')
        if developer_name:
            lines.append(f'  <developer_name>{esc(developer_name)}</developer_name>')
        if cat_list:
            lines.append('  <categories>')
            for cat in cat_list:
                lines.append(f'    <category>{esc(cat)}</category>')
            lines.append('  </categories>')
        if kw_list:
            lines.append('  <keywords>')
            for kw in kw_list:
                lines.append(f'    <keyword>{esc(kw)}</keyword>')
            lines.append('  </keywords>')
        lines.append('  <releases>')
        lines.append(f'    <release version="{esc(version)}" date="{esc(today)}"/>')
        lines.append('  </releases>')
        lines.append('  <content_rating type="oars-1.1"/>')
        lines.append('</component>')
        lines.append('')

        content = "\n".join(lines)

        with open(dest_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)

        # Validate XML is well-formed
        try:
            import xml.etree.ElementTree as ET
            ET.parse(dest_path)
        except Exception:
            pass

        messagebox.showinfo("Debian App Builder", f"Successfully created AppStream metadata:\n{dest_path}")
        return dest_path

    except OSError as error:
        messagebox.showerror(
            "Debian App Builder",
            f"Error while creating AppStream file: {error}",
        )
        return None
    except Exception as error:
        messagebox.showerror(
            "Debian App Builder",
            f"Unexpected error while creating AppStream file: {error}",
        )
        return None


def create_instructions_file(package_root, package_name, desktop_name="", version="", arch="amd64", app_id="", main_file=""):
    """
    Create INSTRUCTIONS.txt inside the package (and caller may copy it next to .deb).
    Every build must produce a text file containing the attribution line,
    with generic usage instructions above it.
    Returns the created file path or None on failure.
    """
    attribution = "This app/package is built using Debian App Builder by tuffgit21 | Official Debian App Builder site: https://tuffgit21.github.io/Debian-App-Builder/ | projects website: https://tuffgit21.github.io/"
    try:
        pkg = str(package_name).strip() or "app"
        ver = str(version).strip() or "1.0"
        arch = str(arch).strip() or "amd64"
        desk = str(desktop_name).strip() or pkg
        app_id = str(app_id).strip()
        main_file = str(main_file).strip()

        # Build instructions content
        deb_name = f"{pkg}_{ver}_{arch}.deb"
        lines = []
        lines.append(f"INSTRUCTIONS - How to use this app ({pkg})")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"Package: {pkg}")
        lines.append(f"Version: {ver}")
        lines.append(f"Architecture: {arch}")
        if app_id:
            lines.append(f"AppStream ID: {app_id}")
        lines.append("")
        lines.append("1) Install the .deb package:")
        lines.append(f"   sudo dpkg -i {deb_name}")
        lines.append("   sudo apt-get install -f   # fix missing dependencies if needed")
        lines.append("   # or: sudo apt install ./" + deb_name)
        lines.append("")
        lines.append("2) Launch the app:")
        lines.append(f"   - Terminal: {pkg}")
        lines.append(f"     (launcher: /usr/bin/{pkg} -> /usr/share/{pkg}/{main_file or '<main file>'})")
        lines.append(f"   - Application menu: Search for \"{desk}\"")
        lines.append(f"     (desktop file: /usr/share/applications/{pkg}.desktop)")
        if main_file:
            lines.append(f"   - Main file: /usr/share/{pkg}/{main_file}")
        lines.append("")
        lines.append("3) Installed files:")
        lines.append(f"   - Application files: /usr/share/{pkg}/")
        lines.append(f"   - Executable wrapper: /usr/bin/{pkg}")
        lines.append(f"   - Desktop entry: /usr/share/applications/{pkg}.desktop")
        lines.append(f"   - Icons (hicolor if generated): /usr/share/icons/hicolor/*/apps/{pkg}.png")
        lines.append(f"   - AppStream metadata (if generated): /usr/share/metainfo/{app_id or pkg}.metainfo.xml")
        lines.append(f"   - This instructions file: /usr/share/{pkg}/INSTRUCTIONS.txt")
        lines.append(f"   - Also available: /usr/share/doc/{pkg}/README")
        lines.append("")
        lines.append("4) Uninstall:")
        lines.append(f"   sudo dpkg -r {pkg}")
        lines.append(f"   # or: sudo apt remove {pkg}")
        lines.append("")
        lines.append("5) Troubleshooting:")
        lines.append("   - If the app needs a terminal window, set Terminal=true in the desktop entry.")
        lines.append("   - Ensure the launcher is executable: sudo chmod 755 /usr/bin/" + pkg)
        lines.append("   - Check desktop file validity: desktop-file-validate /usr/share/applications/" + pkg + ".desktop")
        lines.append("   - Check AppStream validity: appstreamcli validate /usr/share/metainfo/*.metainfo.xml")
        lines.append("   - View logs: run the app from terminal to see output.")
        lines.append("")
        lines.append("6) Rebuilding:")
        lines.append("   - Use Debian App Builder to update files and rebuild the .deb.")
        lines.append("")
        lines.append("-" * 60)
        lines.append(attribution)
        lines.append("")
        content = "\n".join(lines)

        # Inside-package locations (included in .deb)
        dest1 = os.path.join(package_root, "usr", "share", pkg, "INSTRUCTIONS.txt")
        dest2 = os.path.join(package_root, "usr", "share", "doc", pkg, "README")
        # Also doc variant
        for dest in (dest1, dest2):
            try:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "w", encoding="utf-8", newline="\n") as f:
                    f.write(content)
                try:
                    os.chmod(dest, 0o644)
                except OSError:
                    pass
            except OSError:
                continue

        return dest1
    except Exception as e:
        try:
            messagebox.showwarning("Debian App Builder", f"Could not create INSTRUCTIONS file: {e}")
        except Exception:
            pass
        return None