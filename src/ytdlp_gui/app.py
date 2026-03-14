from __future__ import annotations

import json
import os
import queue
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import BooleanVar, Canvas, DoubleVar, Menu, PhotoImage, StringVar, Tk, Toplevel, colorchooser, filedialog, messagebox
from tkinter import font as tkfont
from tkinter import TclError
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from .version import __version__

DOCS_URL = "https://github.com/yt-dlp/yt-dlp#readme"
RELEASE_API_URL = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
RELEASES_API_URL = "https://api.github.com/repos/yt-dlp/yt-dlp/releases"
RELEASE_TAG_API_URL = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/tags/{tag}"

MUSIC_SOURCES: dict[str, dict[str, str]] = {
    "Spotify": {
        "stream_url": "",
        "page_url": "https://open.spotify.com/",
        "now_playing": "",
    },
    "YouTube Music": {
        "stream_url": "",
        "page_url": "https://music.youtube.com/",
        "now_playing": "",
    },
    "SoundCloud": {
        "stream_url": "",
        "page_url": "https://soundcloud.com/",
        "now_playing": "",
    },
    "Deezer": {
        "stream_url": "",
        "page_url": "https://www.deezer.com/",
        "now_playing": "",
    },
    "Newgrounds": {
        "stream_url": "",
        "page_url": "https://www.newgrounds.com/audio",
        "now_playing": "",
    },
    "TIDAL": {
        "stream_url": "",
        "page_url": "https://listen.tidal.com/",
        "now_playing": "",
    },
    "RiMusic": {
        "stream_url": "",
        "page_url": "https://github.com/fast4x/RiMusic",
        "now_playing": "",
    },
    "Local File": {
        "stream_url": "",
        "page_url": "",
        "now_playing": "",
    },
}

DESIGN_TEXTURE = {
    "name": "Asfalt Dark",
    "url": "https://www.transparenttextures.com/patterns/asfalt-dark.png",
    "source": "https://www.transparenttextures.com/",
    "license": "CC BY 3.0",
}

ASSET_ROOT_CANDIDATES = [
    Path("/usr/share/yt-dlp-gui/assets"),
    Path(__file__).resolve().parents[2] / "assets",
]

ICON_CANDIDATES = [
    Path("/usr/share/icons/hicolor/256x256/apps/yt-dlp-gui.png"),
    Path("/usr/share/pixmaps/yt-dlp-gui.png"),
    Path("/usr/share/pixmaps/yt-dlp-gui.ico"),
    Path(__file__).resolve().parents[2] / "assets" / "yt-dlp.png",
    Path(__file__).resolve().parents[2] / "assets" / "yt-dlp.ico",
]

YTDLP_CANDIDATES = [
    Path("/usr/share/yt-dlp-gui/bin/yt-dlp"),
    Path(__file__).resolve().parents[2] / "bin" / "yt-dlp",
]

FORMAT_PROFILES: dict[str, tuple[list[str], str]] = {
    "best": (["-f", "bv*+ba/b"], "Best available quality (video+audio)"),
    "bestvideo": (["-f", "bv*+ba"], "Best separate video + best audio"),
    "bestaudio": (["-f", "ba"], "Best audio stream only"),
    "4k": (["-f", "bv*[height<=2160]+ba/b[height<=2160]"], "Cap video to 4K"),
    "1440": (["-f", "bv*[height<=1440]+ba/b[height<=1440]"], "Cap video to 1440p"),
    "1080": (["-f", "bv*[height<=1080]+ba/b[height<=1080]"], "Cap video to 1080p"),
    "720": (["-f", "bv*[height<=720]+ba/b[height<=720]"], "Cap video to 720p"),
    "480": (["-f", "bv*[height<=480]+ba/b[height<=480]"], "Cap video to 480p"),
    "mp4": (["-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]"], "Prefer MP4-compatible streams"),
    "webm": (["-f", "bv*[ext=webm]+ba[ext=webm]/b[ext=webm]"], "Prefer WebM streams"),
    "audio": (["-x", "-f", "ba"], "Extract audio and convert to selected format"),
    "worst": (["-f", "worst"], "Smallest quality profile"),
    "custom": ([], "Use manual yt-dlp format selector"),
}

REMUX_CONTAINERS = ["auto", "mp4", "mkv", "mov", "webm"]


def _modern_palette() -> dict[str, str]:
    return {
        "window": "#0d1424",
        "surface": "#16223a",
        "panel": "#1e2f4f",
        "header": "#283f67",
        "title": "#f7f9ff",
        "text": "#dbe6ff",
        "accent": "#67d3ff",
        "muted": "#a9bcdf",
        "input_bg": "#f7fbff",
        "input_fg": "#111b2f",
        "tab_bg": "#314d7c",
    }


def _barebones_palette() -> dict[str, str]:
    return {
        "window": "#ffffff",
        "surface": "#ffffff",
        "panel": "#ffffff",
        "header": "#ffffff",
        "title": "#000000",
        "text": "#000000",
        "accent": "#000000",
        "muted": "#000000",
        "input_bg": "#ffffff",
        "input_fg": "#000000",
        "tab_bg": "#ffffff",
    }


class YtDlpGui(Tk):
    def __init__(self) -> None:
        self._configure_display_backend_defaults()
        super().__init__(className="yt-dlp-gui")
        self.title("yt-dlp GUI")
        self.geometry("1240x840")
        self.minsize(1040, 720)

        self.process: subprocess.Popen[str] | None = None
        self.music_process: subprocess.Popen[str] | None = None
        self.music_paused = False
        self.music_polling = False

        self.cache_root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        self.runtime_dir = self.cache_root / "yt-dlp-gui"
        self.crash_log_path = self.runtime_dir / "crash.log"
        self.debug_log_path = self.runtime_dir / "debug.log"
        self.config_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        self.config_dir = self.config_root / "yt-dlp-gui"
        self.settings_path = self.config_dir / "settings.json"

        self.output_queue: queue.Queue[str] = queue.Queue()
        self.latest_stable_version: str | None = None
        self.ytdlp_command = self._resolve_ytdlp_command()

        self.mode_var = BooleanVar(value=False)
        self.barebones_ui_var = BooleanVar(value=False)

        self.url_var = StringVar()
        self.output_dir_var = StringVar(value=str(Path.home() / "Downloads"))
        self.filename_template_var = StringVar(value="%(title)s.%(ext)s")
        self.format_mode_var = StringVar(value="best")
        self.custom_format_var = StringVar(value="")
        self.audio_format_var = StringVar(value="mp3")
        self.remux_container_var = StringVar(value="auto")

        self.subtitles_var = BooleanVar(value=False)
        self.embed_metadata_var = BooleanVar(value=True)
        self.playlist_var = BooleanVar(value=False)
        self.thumbnail_var = BooleanVar(value=False)
        self.embed_thumbnail_var = BooleanVar(value=False)

        self.proxy_var = StringVar()
        self.rate_limit_var = StringVar()
        self.retries_var = StringVar(value="10")
        self.cookies_from_browser_var = StringVar(value="")
        self.additional_args_var = StringVar()

        self.progress_var = DoubleVar(value=0)
        self.status_var = StringVar(value="Ready")
        self.command_preview_var = StringVar(value="")

        self.music_source_var = StringVar(value="Spotify")
        self.local_music_file_var = StringVar(value="")
        self.current_track_var = StringVar(value="Current track: idle")
        self.play_button_var = StringVar(value="Play")
        self.pause_button_var = StringVar(value="Pause")

        self.user_agent_var = StringVar(value="")
        self.referer_var = StringVar(value="")
        self.concurrent_fragments_var = StringVar(value="")
        self.download_sections_var = StringVar(value="")
        self.ignore_errors_var = BooleanVar(value=False)
        self.no_warnings_var = BooleanVar(value=False)

        self._banner_texture: PhotoImage | None = None
        self._banner_canvases: list[Canvas] = []
        self.header_accent_bar: Canvas | None = None
        self.custom_accent_color: str | None = None
        self.custom_bg_color: str | None = None
        self._load_user_settings()
        self.display_backend_full_text = f"Display backend: {self._detect_display_backend()}"
        self.current_version_full_text = "Detecting installed yt-dlp version…"
        self.latest_version_full_text = "Latest stable release: not checked"
        self.docs_url_full_text = DOCS_URL
        self.backend_commands_full_text = (
            "Wayland: GDK_BACKEND=wayland QT_QPA_PLATFORM=wayland SDL_VIDEODRIVER=wayland XDG_SESSION_TYPE=wayland yt-dlp-gui\n"
            "X11: GDK_BACKEND=x11 QT_QPA_PLATFORM=xcb SDL_VIDEODRIVER=x11 XDG_SESSION_TYPE=x11 yt-dlp-gui"
        )
        self.display_backend_label: ttk.Label | None = None
        self.current_version_label: ttk.Label | None = None
        self.latest_version_label: ttk.Label | None = None
        self.docs_url_label: ttk.Label | None = None
        self.backend_commands_label: ttk.Label | None = None
        self.credits_tree: ttk.Treeview | None = None
        self.tools_menu: Menu | None = None
        self.debug_logging_var = BooleanVar(value=True)
        self.stacktrace_dialogs_var = BooleanVar(value=False)

        self.ui_mode_label_var = StringVar(value="UI: Simple" if self.barebones_ui_var.get() else "UI: Color")
        self.current_version_var = StringVar(value=self.current_version_full_text)
        self.latest_version_var = StringVar(value=self.latest_version_full_text)
        self.display_backend_var = StringVar(value=self.display_backend_full_text)

        self._register_preview_watchers()
        self._load_design_texture()
        self._build_style()
        self._set_app_icon()
        self._install_exception_hooks()
        self._build_ui()

        self._load_current_version()
        self.bind("<Control-m>", self._toggle_mode_shortcut)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Configure>", self._on_window_resize)
        self.after(120, self._poll_output)
        self._update_command_preview()

    def _configure_display_backend_defaults(self) -> None:
        if not os.environ.get("GDK_BACKEND"):
            os.environ["GDK_BACKEND"] = "wayland,x11"
        if not os.environ.get("QT_QPA_PLATFORM"):
            os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"
        if not os.environ.get("SDL_VIDEODRIVER"):
            os.environ["SDL_VIDEODRIVER"] = "wayland,x11"
        if not os.environ.get("XDG_SESSION_TYPE") and os.environ.get("WAYLAND_DISPLAY"):
            os.environ["XDG_SESSION_TYPE"] = "wayland"

    def _detect_display_backend(self) -> str:
        if os.environ.get("WAYLAND_DISPLAY"):
            return "Wayland (preferred)"
        if os.environ.get("DISPLAY"):
            return "X11 (fallback)"
        return "Unknown"

    def _ensure_runtime_dir(self) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_ytdlp_command(self) -> str:
        for candidate in YTDLP_CANDIDATES:
            if candidate.exists() and os.access(candidate, os.X_OK):
                return str(candidate)
        discovered = shutil.which("yt-dlp")
        return discovered if discovered else "yt-dlp"

    def _is_writable_executable(self, command: str) -> bool:
        command_path = Path(command)
        if not command_path.is_absolute():
            return True
        return os.access(command_path, os.W_OK)

    def _bundled_target_path(self) -> Path:
        for candidate in YTDLP_CANDIDATES:
            if candidate.is_absolute() and candidate.exists():
                return candidate
        return YTDLP_CANDIDATES[0]

    def _fetch_release_tags(self) -> list[str]:
        tags: list[str] = []
        seen: set[str] = set()
        page = 1
        while page <= 30:
            req = urllib.request.Request(
                f"{RELEASES_API_URL}?per_page=100&page={page}",
                headers={"Accept": "application/vnd.github+json", "User-Agent": "yt-dlp-gui"},
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))

            if not isinstance(payload, list) or not payload:
                break

            for release in payload:
                if not isinstance(release, dict):
                    continue
                tag = str(release.get("tag_name", "")).strip()
                if tag and tag not in seen:
                    seen.add(tag)
                    tags.append(tag)

            if len(payload) < 100:
                break
            page += 1

        return tags

    def _download_github_release_binary(self, tag: str) -> Path:
        req = urllib.request.Request(
            RELEASE_TAG_API_URL.format(tag=urllib.parse.quote(tag, safe="")),
            headers={"Accept": "application/vnd.github+json", "User-Agent": "yt-dlp-gui"},
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assets = payload.get("assets", []) if isinstance(payload, dict) else []
        download_url: str | None = None
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            if str(asset.get("name", "")).strip() == "yt-dlp":
                download_url = str(asset.get("browser_download_url", "")).strip()
                break

        if not download_url:
            raise RuntimeError(f"Release {tag} does not contain a Linux yt-dlp binary asset.")

        self._ensure_runtime_dir()
        download_path = self.runtime_dir / f"yt-dlp-{tag}"
        req_bin = urllib.request.Request(download_url, headers={"User-Agent": "yt-dlp-gui"})
        with urllib.request.urlopen(req_bin, timeout=60) as response:
            download_path.write_bytes(response.read())
        os.chmod(download_path, 0o755)
        return download_path

    def _apply_downloaded_binary(self, downloaded_binary: Path) -> None:
        target = self._bundled_target_path()
        if self._is_writable_executable(str(target)):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(downloaded_binary, target)
            os.chmod(target, 0o755)
            return

        pkexec = shutil.which("pkexec")
        if not pkexec:
            raise RuntimeError("Writing bundled yt-dlp requires elevated privileges (pkexec not found).")

        result = subprocess.run(
            [pkexec, "install", "-m", "755", str(downloaded_binary), str(target)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise RuntimeError(stderr or "Failed to install selected yt-dlp version.")

    def _install_github_version(self, tag: str) -> None:
        self.status_var.set(f"Downloading yt-dlp {tag}…")
        try:
            downloaded = self._download_github_release_binary(tag)
            self.status_var.set(f"Applying yt-dlp {tag}…")
            self._apply_downloaded_binary(downloaded)
            self.ytdlp_command = self._resolve_ytdlp_command()
            self._append_log(f"Installed GitHub release {tag} into bundled yt-dlp")
            self.status_var.set(f"Installed yt-dlp {tag}")
            self._load_current_version()
            self._check_updates()
        except Exception as err:
            self.status_var.set("Version install failed")
            messagebox.showerror("Install GitHub version failed", str(err))

    def _open_github_version_installer(self) -> None:
        self.status_var.set("Loading official GitHub release list…")
        try:
            tags = self._fetch_release_tags()
            current_tag = self._installed_version()
        except Exception as err:
            self.status_var.set("Could not load release list")
            messagebox.showerror("Release list failed", str(err))
            return

        if not tags:
            self.status_var.set("No releases found")
            messagebox.showerror("Release list failed", "No releases were returned by GitHub.")
            return

        self.status_var.set("Select a release to install")
        dialog = Toplevel(self)
        dialog.title("Install official GitHub yt-dlp version")
        dialog.geometry("520x150")
        dialog.minsize(460, 140)
        dialog.transient(self)

        frame = ttk.Frame(dialog, style="App.TFrame", padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)

        installed_text = current_tag if current_tag else "unavailable"
        ttk.Label(frame, text=f"Installed: {installed_text}", style="App.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 4))
        ttk.Label(frame, text="Select version tag", style="App.TLabel").grid(row=1, column=0, sticky="w")
        selected_tag = current_tag if current_tag in tags else tags[0]
        tag_var = StringVar(value=selected_tag)
        combo = ttk.Combobox(frame, textvariable=tag_var, values=tags, state="readonly")
        combo.grid(row=2, column=0, sticky="ew", pady=(6, 10))

        buttons = ttk.Frame(frame, style="App.TFrame")
        buttons.grid(row=3, column=0, sticky="e")

        def _install_selected() -> None:
            tag = tag_var.get().strip()
            if not tag:
                messagebox.showerror("Missing version", "Pick a release version first.")
                return
            dialog.destroy()
            threading.Thread(target=self._install_github_version, args=(tag,), daemon=True).start()

        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text="Install Selected Version", style="Accent.TButton", command=_install_selected).pack(side="right", padx=(0, 8))

    def _ensure_config_dir(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def _normalize_hex_color(self, value: object) -> str | None:
        if not isinstance(value, str):
            return None
        raw = value.strip()
        if not raw:
            return None
        if raw.startswith("#"):
            candidate = raw
        else:
            candidate = f"#{raw}"
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", candidate):
            return None
        return candidate.lower()

    def _load_user_settings(self) -> None:
        try:
            if not self.settings_path.exists():
                return
            payload = json.loads(self.settings_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return

            barebones = payload.get("barebones_ui")
            if isinstance(barebones, bool):
                self.barebones_ui_var.set(barebones)

            expert_enabled = payload.get("expert_enabled")
            if isinstance(expert_enabled, bool):
                self.mode_var.set(expert_enabled)

            self.custom_accent_color = self._normalize_hex_color(payload.get("custom_accent_color"))
            self.custom_bg_color = self._normalize_hex_color(payload.get("custom_bg_color"))
        except Exception:
            return

    def _save_user_settings(self) -> None:
        payload = {
            "barebones_ui": self.barebones_ui_var.get(),
            "expert_enabled": self.mode_var.get(),
            "custom_accent_color": self.custom_accent_color,
            "custom_bg_color": self.custom_bg_color,
        }
        try:
            self._ensure_config_dir()
            self.settings_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            return

    def _debug_log(self, message: str) -> None:
        if not self.debug_logging_var.get():
            return
        try:
            self._ensure_runtime_dir()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with self.debug_log_path.open("a", encoding="utf-8") as handle:
                handle.write(f"[{timestamp}] {message}\n")
        except Exception:
            pass

    def _write_crash_log(self, context: str, err: BaseException, tb_text: str) -> None:
        self._ensure_runtime_dir()
        process_info = self._runtime_process_info_text()
        payload = (
            f"Timestamp: {datetime.now().isoformat()}\n"
            f"Context: {context}\n"
            f"Error: {err}\n"
            f"\nProcess info:\n{process_info}\n"
            f"\n{tb_text}"
        )
        self.crash_log_path.write_text(payload, encoding="utf-8")
        self._debug_log(f"Crash logged in {context}: {err}")

    def _runtime_process_info_text(self) -> str:
        return "\n".join(
            [
                f"PID: {os.getpid()}",
                f"PPID: {os.getppid()}",
                f"CWD: {Path.cwd()}",
                f"Python executable: {sys.executable}",
                f"Python version: {sys.version.split()[0]}",
                f"yt-dlp command: {self.ytdlp_command}",
                f"Display backend: {self._detect_display_backend()}",
            ]
        )

    def _compose_crash_details(self, context: str, err: BaseException, tb_text: str) -> str:
        return (
            f"Context: {context}\n"
            f"Error: {err}\n\n"
            f"Process info:\n{self._runtime_process_info_text()}\n\n"
            f"Stack trace:\n{tb_text}\n"
            f"Crash log: {self.crash_log_path}"
        )

    def _show_crash_details_popup(self, title: str, details: str) -> None:
        try:
            self._open_log_file(self.crash_log_path)
        except Exception:
            pass

        try:
            dialog = Toplevel(self)
            dialog.title(title)
            dialog.geometry("980x620")
            dialog.minsize(780, 480)
            dialog.transient(self)

            frame = ttk.Frame(dialog, style="App.TFrame", padding=12)
            frame.pack(fill="both", expand=True)
            frame.columnconfigure(0, weight=1)
            frame.rowconfigure(1, weight=1)

            ttk.Label(
                frame,
                text="A crash was captured. The crash log has been opened.",
                style="App.TLabel",
            ).grid(row=0, column=0, sticky="w", pady=(0, 8))

            details_view = ScrolledText(frame, wrap="word", font=("Consolas", 10))
            details_view.grid(row=1, column=0, sticky="nsew")
            details_view.insert("end", details)
            details_view.configure(state="disabled")

            button_row = ttk.Frame(frame, style="App.TFrame")
            button_row.grid(row=2, column=0, sticky="e", pady=(10, 0))
            ttk.Button(button_row, text="Close", command=dialog.destroy).pack(side="right")

            dialog.grab_set()
            dialog.focus_force()
            dialog.wait_window()
        except Exception:
            messagebox.showerror(title, details)

    def _install_exception_hooks(self) -> None:
        def _sys_hook(exc_type: type[BaseException], value: BaseException, tb: object) -> None:
            tb_text = "".join(traceback.format_exception(exc_type, value, tb))
            self._write_crash_log("sys.excepthook", value, tb_text)
            details = self._compose_crash_details("sys.excepthook", value, tb_text)
            try:
                self._show_crash_details_popup("Unhandled crash detected", details)
            except Exception:
                pass
            print(tb_text, flush=True)

        def _thread_hook(args: threading.ExceptHookArgs) -> None:
            tb_text = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
            self._write_crash_log("threading.excepthook", args.exc_value, tb_text)
            details = self._compose_crash_details("threading.excepthook", args.exc_value, tb_text)
            try:
                self.after(0, lambda: self._show_crash_details_popup("Thread crash detected", details))
            except Exception:
                pass
            self._debug_log(f"Thread exception in {args.thread.name}: {args.exc_value}")

        sys.excepthook = _sys_hook
        threading.excepthook = _thread_hook

    def report_callback_exception(self, exc: type[BaseException], val: BaseException, tb: object) -> None:
        tb_text = "".join(traceback.format_exception(exc, val, tb))
        self._write_crash_log("tk.callback", val, tb_text)
        details = self._compose_crash_details("tk.callback", val, tb_text)
        self._show_crash_details_popup("Application crash detected", details)

    def _open_log_file(self, path: Path) -> None:
        try:
            self._ensure_runtime_dir()
            if not path.exists():
                path.write_text("", encoding="utf-8")
            webbrowser.open(path.as_uri())
        except Exception as err:
            messagebox.showerror("Could not open log file", str(err))

    def _copy_runtime_diagnostics(self) -> None:
        details = [
            f"Display backend: {self._detect_display_backend()}",
            f"Python: {sys.version.split()[0]}",
            f"Crash log: {self.crash_log_path}",
            f"Debug log: {self.debug_log_path}",
            f"yt-dlp command: {self.ytdlp_command}",
            f"yt-dlp in PATH: {'yes' if shutil.which('yt-dlp') else 'no'}",
            f"pacman in PATH: {'yes' if shutil.which('pacman') else 'no'}",
            f"pkexec in PATH: {'yes' if shutil.which('pkexec') else 'no'}",
        ]
        text = "\n".join(details)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_var.set("Runtime diagnostics copied")
        self._debug_log("Runtime diagnostics copied to clipboard")

    def _simulate_crash(self) -> None:
        err = RuntimeError("Manual crash triggered from Dev menu")
        tb_text = "".join(traceback.format_stack())
        self._write_crash_log("manual.crash_test", err, tb_text)
        details = self._compose_crash_details("manual.crash_test", err, tb_text)
        self._show_crash_details_popup("Crash test activated", details)
        if self.process and self.process.poll() is None:
            self.process.terminate()
        self._stop_music()
        self._save_user_settings()
        os._exit(1)

    def _register_preview_watchers(self) -> None:
        tracked_vars = [
            self.url_var,
            self.output_dir_var,
            self.filename_template_var,
            self.format_mode_var,
            self.custom_format_var,
            self.audio_format_var,
            self.remux_container_var,
            self.subtitles_var,
            self.embed_metadata_var,
            self.playlist_var,
            self.thumbnail_var,
            self.embed_thumbnail_var,
            self.proxy_var,
            self.rate_limit_var,
            self.retries_var,
            self.cookies_from_browser_var,
            self.additional_args_var,
            self.user_agent_var,
            self.referer_var,
            self.concurrent_fragments_var,
            self.download_sections_var,
            self.ignore_errors_var,
            self.no_warnings_var,
            self.mode_var,
        ]
        for variable in tracked_vars:
            variable.trace_add("write", self._trace_refresh)

    def _trace_refresh(self, *_args: object) -> None:
        self._update_command_preview()

    def _shade(self, hex_color: str, factor: float) -> str:
        value = hex_color.strip().lstrip("#")
        if len(value) != 6:
            return hex_color
        try:
            red = int(value[0:2], 16)
            green = int(value[2:4], 16)
            blue = int(value[4:6], 16)
        except ValueError:
            return hex_color

        def clamp(channel: int) -> int:
            return max(0, min(255, int(channel * factor)))

        return f"#{clamp(red):02x}{clamp(green):02x}{clamp(blue):02x}"

    def _is_dark_color(self, hex_color: str) -> bool:
        value = hex_color.strip().lstrip("#")
        if len(value) != 6:
            return False
        try:
            red = int(value[0:2], 16) / 255.0
            green = int(value[2:4], 16) / 255.0
            blue = int(value[4:6], 16) / 255.0
        except ValueError:
            return False

        def linearize(channel: float) -> float:
            if channel <= 0.03928:
                return channel / 12.92
            return ((channel + 0.055) / 1.055) ** 2.4

        luminance = 0.2126 * linearize(red) + 0.7152 * linearize(green) + 0.0722 * linearize(blue)
        return luminance < 0.45

    def _active_palette(self) -> dict[str, str]:
        pal = (_barebones_palette() if self.barebones_ui_var.get() else _modern_palette()).copy()
        if not self.barebones_ui_var.get() and self.custom_bg_color:
            base = self.custom_bg_color
            pal["window"] = self._shade(base, 0.34)
            pal["surface"] = self._shade(base, 0.46)
            pal["panel"] = self._shade(base, 0.56)
            pal["header"] = self._shade(base, 0.70)
            pal["tab_bg"] = self._shade(base, 0.62)
            pal["muted"] = self._shade(base, 1.25)
            pal["input_bg"] = self._shade(base, 1.95)
            pal["input_fg"] = "#ecf3ff" if self._is_dark_color(pal["input_bg"]) else "#0f1729"
        if not self.barebones_ui_var.get() and self.custom_accent_color:
            pal["accent"] = self.custom_accent_color
        return pal

    def _refresh_visual_theme(self) -> None:
        style = ttk.Style(self)
        self._apply_palette(style)

        pal = self._active_palette()
        if hasattr(self, "log"):
            self.log.configure(bg=pal["input_bg"], fg=pal["input_fg"])

        if self.header_accent_bar and self.header_accent_bar.winfo_exists():
            self.header_accent_bar.configure(bg=pal["accent"])

        refreshed: list[Canvas] = []
        for canvas in self._banner_canvases:
            if canvas.winfo_exists():
                canvas.event_generate("<Configure>")
                refreshed.append(canvas)
        self._banner_canvases = refreshed

        self._apply_responsive_text()

    def _pick_accent_color(self) -> None:
        if self.barebones_ui_var.get():
            messagebox.showinfo("Color picker", "Switch to Color UI mode to customize motif color.")
            return
        current = self.custom_accent_color or _modern_palette()["accent"]
        selected = colorchooser.askcolor(color=current, title="Pick motif accent color")
        hex_color = selected[1]
        if not hex_color:
            return
        self.custom_accent_color = hex_color
        self._refresh_visual_theme()

    def _reset_accent_color(self) -> None:
        self.custom_accent_color = None
        self._refresh_visual_theme()

    def _pick_background_color(self) -> None:
        if self.barebones_ui_var.get():
            messagebox.showinfo("Color picker", "Background color is disabled in Simple UI mode.")
            return
        current = self.custom_bg_color or _modern_palette()["panel"]
        selected = colorchooser.askcolor(color=current, title="Pick UI background color")
        hex_color = selected[1]
        if not hex_color:
            return
        self.custom_bg_color = hex_color
        self._refresh_visual_theme()

    def _reset_background_color(self) -> None:
        self.custom_bg_color = None
        self._refresh_visual_theme()

    def _truncate_to_width(self, text: str, max_pixels: int, widget: ttk.Label) -> str:
        if max_pixels <= 0:
            return ""
        font_name = str(widget.cget("font") or "TkDefaultFont")
        font_obj = tkfont.nametofont(font_name)
        if font_obj.measure(text) <= max_pixels:
            return text
        ellipsis = "…"
        ellipsis_width = font_obj.measure(ellipsis)
        if ellipsis_width >= max_pixels:
            return ""

        end = len(text)
        while end > 0 and font_obj.measure(text[:end]) + ellipsis_width > max_pixels:
            end -= 1
        return (text[:end].rstrip() + ellipsis) if end > 0 else ellipsis

    def _apply_responsive_text(self) -> None:
        window_width = self.winfo_width()

        if self.current_version_label and self.current_version_label.winfo_exists():
            if window_width >= 1280:
                self.current_version_var.set(self.current_version_full_text)
            else:
                width = max(80, self.current_version_label.winfo_width() - 8)
                self.current_version_var.set(self._truncate_to_width(self.current_version_full_text, width, self.current_version_label))

        if self.display_backend_label and self.display_backend_label.winfo_exists():
            if window_width >= 1280:
                self.display_backend_var.set(self.display_backend_full_text)
            else:
                width = max(80, self.display_backend_label.winfo_width() - 8)
                self.display_backend_var.set(self._truncate_to_width(self.display_backend_full_text, width, self.display_backend_label))

        if self.latest_version_label and self.latest_version_label.winfo_exists():
            if window_width >= 1180:
                self.latest_version_var.set(self.latest_version_full_text)
            else:
                width = max(80, self.latest_version_label.winfo_width() - 8)
                self.latest_version_var.set(self._truncate_to_width(self.latest_version_full_text, width, self.latest_version_label))

        if self.docs_url_label and self.docs_url_label.winfo_exists():
            width = max(140, self.docs_url_label.winfo_width() - 8)
            self.docs_url_label.configure(text=self._truncate_to_width(self.docs_url_full_text, width, self.docs_url_label))

        if self.backend_commands_label and self.backend_commands_label.winfo_exists():
            width = max(260, self.backend_commands_label.winfo_width() - 10)
            self.backend_commands_label.configure(wraplength=width, text=self.backend_commands_full_text)

        if self.credits_tree and self.credits_tree.winfo_exists():
            total_width = max(360, self.credits_tree.winfo_width())
            asset_w = max(120, int(total_width * 0.24))
            source_w = max(180, int(total_width * 0.50))
            license_w = max(120, total_width - asset_w - source_w - 8)
            self.credits_tree.column("asset", width=asset_w)
            self.credits_tree.column("source", width=source_w)
            self.credits_tree.column("license", width=license_w)

    def _on_window_resize(self, _event: object) -> None:
        self.after_idle(self._apply_responsive_text)

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        self._apply_palette(style)

    def _apply_palette(self, style: ttk.Style) -> None:
        pal = self._active_palette()
        is_barebones = self.barebones_ui_var.get()

        self.configure(bg=pal["window"])
        style.configure("App.TFrame", background=pal["surface"])
        style.configure("Panel.TFrame", background=pal["panel"])
        style.configure("Header.TFrame", background=pal["header"])
        base_font = "TkDefaultFont" if is_barebones else "Verdana"
        style.configure("Header.TLabel", background=pal["header"], foreground=pal["title"], font=(base_font, 10, "bold"))
        style.configure("App.TLabel", background=pal["surface"], foreground=pal["text"], font=(base_font, 10))
        style.configure("Panel.TLabel", background=pal["panel"], foreground=pal["text"], font=(base_font, 10))
        style.configure("App.TCheckbutton", background=pal["surface"], foreground=pal["text"], font=(base_font, 10))
        style.configure("TButton", padding=6 if is_barebones else 7)
        style.map("TButton", background=[("active", pal["tab_bg"])], foreground=[("active", pal["title"])])
        style.configure("Accent.TButton", font=(base_font, 10, "bold"), padding=6 if is_barebones else 7)
        if not is_barebones:
            style.map("Accent.TButton", background=[("!disabled", pal["accent"]), ("active", "#44c6ff")], foreground=[("!disabled", "#0b2236")])
        style.configure("Mode.TButton", font=(base_font, 10, "bold"), padding=6 if is_barebones else 9)

        frame_relief = "flat" if is_barebones else "ridge"
        frame_border = 1 if is_barebones else 2
        style.configure("Card.TLabelframe", background=pal["surface"], foreground=pal["accent"], borderwidth=frame_border, relief=frame_relief)
        style.configure("Card.TLabelframe.Label", background=pal["surface"], foreground=pal["accent"], font=(base_font, 10, "bold"))
        style.configure("PanelCard.TLabelframe", background=pal["panel"], foreground=pal["accent"], borderwidth=frame_border, relief=frame_relief)
        style.configure("PanelCard.TLabelframe.Label", background=pal["panel"], foreground=pal["accent"], font=(base_font, 10, "bold"))

        style.configure("Vintage.Treeview", font=(base_font, 9), rowheight=22 if is_barebones else 24)
        style.configure("Vintage.Treeview.Heading", font=(base_font, 9, "bold"))

        style.configure("TNotebook", background=pal["window"], borderwidth=0)
        style.configure("TNotebook.Tab", background=pal["tab_bg"], foreground=pal["text"], padding=(10 if is_barebones else 14, 6 if is_barebones else 8), font=(base_font, 10, "bold"))
        style.map(
            "TNotebook.Tab",
            background=[("selected", pal["accent"]), ("!selected", pal["tab_bg"])],
            foreground=[("selected", pal["panel"] if not is_barebones else "#ffffff"), ("!selected", pal["text"])],
        )

    def _set_app_icon(self) -> None:
        for icon_path in ICON_CANDIDATES:
            if not icon_path.exists():
                continue
            try:
                if icon_path.suffix.lower() == ".png":
                    image = PhotoImage(file=str(icon_path))
                    self.iconphoto(True, image)
                    self._icon_ref = image
                else:
                    self.iconbitmap(str(icon_path))
                return
            except Exception:
                continue

    def _load_design_texture(self) -> None:
        cache_root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        texture_dir = cache_root / "yt-dlp-gui"
        texture_path = texture_dir / "design-texture.png"
        try:
            if not texture_path.exists():
                texture_dir.mkdir(parents=True, exist_ok=True)
                req = urllib.request.Request(DESIGN_TEXTURE["url"], headers={"User-Agent": "yt-dlp-gui"})
                with urllib.request.urlopen(req, timeout=10) as response:
                    texture_path.write_bytes(response.read())
            self._banner_texture = PhotoImage(file=str(texture_path))
        except Exception:
            self._banner_texture = None

    def _build_ui(self) -> None:
        self._build_menubar()

        self.container = ttk.Frame(self, style="App.TFrame", padding=10)
        self.container.pack(fill="both", expand=True)

        header = ttk.Frame(self.container, style="Header.TFrame", padding=(12, 10))
        header.pack(fill="x", padx=4, pady=(4, 8))
        header.columnconfigure(0, weight=1)
        header.columnconfigure(1, weight=1)
        header.columnconfigure(2, weight=0)

        self.header_accent_bar = Canvas(header, height=5, highlightthickness=0, bd=0)
        self.header_accent_bar.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        self.header_accent_bar.configure(bg=self._active_palette()["accent"])

        self.title_label = ttk.Label(header, text="yt-dlp GUI", style="Header.TLabel")
        self.title_label.grid(row=1, column=0, sticky="w")

        info_frame = ttk.Frame(header, style="Header.TFrame")
        info_frame.grid(row=1, column=1, sticky="ew", padx=(10, 10))
        info_frame.columnconfigure(0, weight=1)

        self.mode_button = ttk.Button(header, text=self._mode_button_text(), style="Mode.TButton", command=self._toggle_mode)
        controls = ttk.Frame(header, style="Header.TFrame")
        controls.grid(row=1, column=2, sticky="e")
        self.mode_button.pack(in_=controls, side="right")

        self.ui_button = ttk.Button(header, text=self.ui_mode_label_var.get(), style="Mode.TButton", command=self._toggle_ui_mode)
        self.ui_button.pack(in_=controls, side="right", padx=(0, 8))

        self.display_backend_label = ttk.Label(header, textvariable=self.display_backend_var, style="Header.TLabel")
        self.display_backend_label.configure(anchor="e")
        self.display_backend_label.grid(in_=info_frame, row=0, column=0, sticky="ew")
        self.current_version_label = ttk.Label(header, textvariable=self.current_version_var, style="Header.TLabel")
        self.current_version_label.configure(anchor="e")
        self.current_version_label.grid(in_=info_frame, row=1, column=0, sticky="ew", pady=(2, 0))

        self.notebook = ttk.Notebook(self.container)
        self.notebook.pack(fill="both", expand=True)

        self.download_tab = ttk.Frame(self.notebook, style="App.TFrame")
        self.activity_tab = ttk.Frame(self.notebook, style="App.TFrame")
        self.help_tab = ttk.Frame(self.notebook, style="App.TFrame")
        self.credits_tab = ttk.Frame(self.notebook, style="App.TFrame")
        self.expert_tab = ttk.Frame(self.notebook, style="App.TFrame")

        self.notebook.add(self.download_tab, text="Download")
        self.notebook.add(self.activity_tab, text="Activity")
        self.notebook.add(self.help_tab, text="Help")
        self.notebook.add(self.credits_tab, text="Credits")

        self._build_download_tab()
        self._build_activity_tab()
        self._build_help_tab()
        self._build_credits_tab()
        self._build_expert_tab()

    def _build_menubar(self) -> None:
        menubar = Menu(self, tearoff=0)

        file_menu = Menu(menubar, tearoff=0)
        file_menu.add_command(label="Start Download", command=self._start_download)
        file_menu.add_command(label="Stop Download", command=self._stop_download)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        view_menu = Menu(menubar, tearoff=0)
        view_menu.add_command(label="Toggle Simple / Color UI", command=self._toggle_ui_mode)
        view_menu.add_command(label="Enable / Disable Expert", command=self._toggle_mode)
        view_menu.add_separator()
        view_menu.add_command(label="Pick Accent Color", command=self._pick_accent_color)
        view_menu.add_command(label="Reset Accent Color", command=self._reset_accent_color)
        view_menu.add_command(label="Pick Background Color", command=self._pick_background_color)
        view_menu.add_command(label="Reset Background Color", command=self._reset_background_color)
        menubar.add_cascade(label="View", menu=view_menu)

        tools_menu = Menu(menubar, tearoff=0)
        tools_menu.add_command(label="List Formats for URL", command=self._list_formats)
        tools_menu.add_command(label="Check Stable Updates", command=self._check_updates_thread)
        tools_menu.add_command(label="Update yt-dlp", command=self._run_update_flow)
        tools_menu.add_command(label="Install GitHub Version…", command=self._open_github_version_installer)
        tools_menu.add_separator()
        tools_menu.add_command(label="Copy Command Preview", command=self._copy_command_preview)
        tools_menu.add_command(label="Clear Activity Log", command=self._clear_log)
        tools_menu.add_command(label="Toggle Music", command=self._toggle_music)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        self.tools_menu = tools_menu

        help_menu = Menu(menubar, tearoff=0)
        help_menu.add_command(label="Open Official Documentation", command=lambda: webbrowser.open(DOCS_URL))
        help_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        dev_menu = Menu(menubar, tearoff=0)
        dev_menu.add_checkbutton(label="Enable Debug Logging", variable=self.debug_logging_var)
        dev_menu.add_checkbutton(label="Show Stack Traces in Dialogs", variable=self.stacktrace_dialogs_var)
        dev_menu.add_separator()
        dev_menu.add_command(label="Open Crash Log", command=lambda: self._open_log_file(self.crash_log_path))
        dev_menu.add_command(label="Open Debug Log", command=lambda: self._open_log_file(self.debug_log_path))
        dev_menu.add_command(label="Copy Runtime Diagnostics", command=self._copy_runtime_diagnostics)
        dev_menu.add_separator()
        dev_menu.add_command(label="Trigger Test Crash", command=self._simulate_crash)
        menubar.add_cascade(label="Dev", menu=dev_menu)

        self.config(menu=menubar)

    def _add_custom_banner(self, parent: ttk.Frame, title: str) -> None:
        self._banner_canvases.clear()
        return

    def _build_download_tab(self) -> None:
        self._add_custom_banner(self.download_tab, "Download Workspace")

        content = ttk.Frame(self.download_tab, style="App.TFrame")
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=3)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        left = ttk.Frame(content, style="App.TFrame")
        left.grid(row=0, column=0, sticky="nsew")

        right = ttk.Frame(content, style="Panel.TFrame", padding=8)
        right.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)
        self.vibe_panel = right

        core = ttk.LabelFrame(left, text="Core options", style="Card.TLabelframe", padding=10)
        core.pack(fill="x", padx=10, pady=(10, 8))

        ttk.Label(core, text="Video / Playlist URL", style="App.TLabel").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(core, textvariable=self.url_var, width=96).grid(row=0, column=1, columnspan=4, sticky="ew", pady=4)

        ttk.Label(core, text="Save folder", style="App.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(core, textvariable=self.output_dir_var, width=74).grid(row=1, column=1, columnspan=3, sticky="ew", pady=4)
        ttk.Button(core, text="Browse", command=self._choose_output_dir).grid(row=1, column=4, sticky="ew", padx=(6, 0))

        ttk.Label(core, text="File name template", style="App.TLabel").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(core, textvariable=self.filename_template_var).grid(row=2, column=1, columnspan=4, sticky="ew", pady=4)

        ttk.Label(core, text="Download profile", style="App.TLabel").grid(row=3, column=0, sticky="w", pady=4)
        self.format_combo = ttk.Combobox(core, textvariable=self.format_mode_var, state="readonly", values=list(FORMAT_PROFILES.keys()), width=18)
        self.format_combo.grid(row=3, column=1, sticky="w", pady=4)
        self.format_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_mode_state())

        self.profile_hint = ttk.Label(core, text="", style="App.TLabel")
        self.profile_hint.grid(row=3, column=2, columnspan=3, sticky="w")

        ttk.Label(core, text="Custom format", style="App.TLabel").grid(row=4, column=0, sticky="w", pady=4)
        self.custom_format_entry = ttk.Entry(core, textvariable=self.custom_format_var)
        self.custom_format_entry.grid(row=4, column=1, columnspan=4, sticky="ew", pady=4)

        ttk.Label(core, text="Audio convert to", style="App.TLabel").grid(row=5, column=0, sticky="w", pady=4)
        self.audio_combo = ttk.Combobox(
            core,
            textvariable=self.audio_format_var,
            state="readonly",
            values=["mp3", "m4a", "opus", "wav", "flac", "aac", "vorbis"],
            width=12,
        )
        self.audio_combo.grid(row=5, column=1, sticky="w", pady=4)

        ttk.Label(core, text="Remux container", style="App.TLabel").grid(row=5, column=2, sticky="w", pady=4)
        self.remux_combo = ttk.Combobox(core, textvariable=self.remux_container_var, state="readonly", values=REMUX_CONTAINERS, width=12)
        self.remux_combo.grid(row=5, column=3, sticky="w", pady=4)

        toggles = ttk.Frame(core, style="App.TFrame")
        toggles.grid(row=6, column=0, columnspan=5, sticky="ew", pady=(8, 2))
        for i in range(3):
            toggles.columnconfigure(i, weight=1)
        ttk.Checkbutton(toggles, text="Download full playlist", variable=self.playlist_var, style="App.TCheckbutton").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 2))
        ttk.Checkbutton(toggles, text="Download subtitles", variable=self.subtitles_var, style="App.TCheckbutton").grid(row=0, column=1, sticky="w", padx=(0, 8), pady=(0, 2))
        ttk.Checkbutton(toggles, text="Embed metadata", variable=self.embed_metadata_var, style="App.TCheckbutton").grid(row=0, column=2, sticky="w", pady=(0, 2))
        ttk.Checkbutton(toggles, text="Save thumbnail", variable=self.thumbnail_var, style="App.TCheckbutton").grid(row=1, column=0, sticky="w", padx=(0, 8))
        ttk.Checkbutton(toggles, text="Embed thumbnail", variable=self.embed_thumbnail_var, style="App.TCheckbutton").grid(row=1, column=1, sticky="w", padx=(0, 8))

        for i in range(5):
            core.columnconfigure(i, weight=1 if i in (1, 2, 3) else 0)

        run_box = ttk.LabelFrame(left, text="Run", style="Card.TLabelframe", padding=10)
        run_box.pack(fill="x", padx=10, pady=(0, 10))

        ttk.Label(run_box, text="Command preview", style="App.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(run_box, textvariable=self.command_preview_var).grid(row=0, column=1, columnspan=6, sticky="ew", pady=(0, 8))

        self.progress = ttk.Progressbar(run_box, mode="determinate", maximum=100, variable=self.progress_var)
        self.progress.grid(row=1, column=0, columnspan=7, sticky="ew", pady=(0, 8))

        ttk.Label(run_box, textvariable=self.status_var, style="App.TLabel").grid(row=2, column=0, columnspan=7, sticky="w", pady=(0, 8))

        ttk.Button(run_box, text="Start Download", style="Accent.TButton", command=self._start_download).grid(row=3, column=0, sticky="ew", padx=(0, 6), pady=(0, 4))
        ttk.Button(run_box, text="Stop", command=self._stop_download).grid(row=3, column=1, sticky="ew", padx=(0, 6), pady=(0, 4))
        ttk.Button(run_box, text="List Formats", command=self._list_formats).grid(row=3, column=2, sticky="ew", padx=(0, 6), pady=(0, 4))
        ttk.Button(run_box, text="Check Stable Updates", command=self._check_updates_thread).grid(row=3, column=3, sticky="ew", padx=(0, 6), pady=(0, 4))
        ttk.Button(run_box, text="Update yt-dlp", command=self._run_update_flow).grid(row=4, column=0, columnspan=2, sticky="ew", padx=(0, 6))
        ttk.Button(run_box, text="Copy Command", command=self._copy_command_preview).grid(row=4, column=2, columnspan=2, sticky="ew", padx=(0, 6))
        self.latest_version_label = ttk.Label(run_box, textvariable=self.latest_version_var, style="App.TLabel")
        self.latest_version_label.grid(row=4, column=4, columnspan=3, sticky="ew")

        for i in range(7):
            run_box.columnconfigure(i, weight=1)

        self._build_music_panel(right)
        self._refresh_mode_state()
        self.after_idle(self._apply_responsive_text)

    def _build_expert_tab(self) -> None:
        outer = ttk.Frame(self.expert_tab, style="App.TFrame", padding=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)

        box = ttk.LabelFrame(outer, text="Expert Options", style="Card.TLabelframe", padding=10)
        box.pack(fill="x")
        box.columnconfigure(1, weight=1)
        box.columnconfigure(3, weight=1)

        ttk.Label(box, text="Proxy URL", style="App.TLabel").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(box, textvariable=self.proxy_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(box, text="Rate limit (ex: 2M)", style="App.TLabel").grid(row=0, column=2, sticky="w", padx=(14, 4), pady=4)
        ttk.Entry(box, textvariable=self.rate_limit_var).grid(row=0, column=3, sticky="ew", pady=4)

        ttk.Label(box, text="Retries", style="App.TLabel").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(box, textvariable=self.retries_var).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(box, text="Cookies from browser", style="App.TLabel").grid(row=1, column=2, sticky="w", padx=(14, 4), pady=4)
        ttk.Entry(box, textvariable=self.cookies_from_browser_var).grid(row=1, column=3, sticky="ew", pady=4)

        ttk.Label(box, text="User-Agent", style="App.TLabel").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(box, textvariable=self.user_agent_var).grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Label(box, text="Referer", style="App.TLabel").grid(row=2, column=2, sticky="w", padx=(14, 4), pady=4)
        ttk.Entry(box, textvariable=self.referer_var).grid(row=2, column=3, sticky="ew", pady=4)

        ttk.Label(box, text="Concurrent fragments", style="App.TLabel").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Entry(box, textvariable=self.concurrent_fragments_var).grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Label(box, text="Download sections", style="App.TLabel").grid(row=3, column=2, sticky="w", padx=(14, 4), pady=4)
        ttk.Entry(box, textvariable=self.download_sections_var).grid(row=3, column=3, sticky="ew", pady=4)

        ttk.Label(box, text="Additional raw yt-dlp args", style="App.TLabel").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Entry(box, textvariable=self.additional_args_var).grid(row=4, column=1, columnspan=3, sticky="ew", pady=4)

        flags = ttk.Frame(box, style="App.TFrame")
        flags.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(8, 4))
        flags.columnconfigure(0, weight=1)
        flags.columnconfigure(1, weight=1)
        ttk.Checkbutton(flags, text="Ignore errors", variable=self.ignore_errors_var, style="App.TCheckbutton").grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(flags, text="Suppress warnings", variable=self.no_warnings_var, style="App.TCheckbutton").grid(row=0, column=1, sticky="w")

        ttk.Label(
            outer,
            text="These options apply only when Expert is enabled.",
            style="App.TLabel",
        ).pack(anchor="w", pady=(10, 0))

    def _build_music_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.LabelFrame(parent, text="Music Controls", style="PanelCard.TLabelframe", padding=8)
        panel.pack(fill="both", expand=True)

        ttk.Label(panel, text="Source", style="Panel.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Combobox(panel, textvariable=self.music_source_var, state="readonly", values=list(MUSIC_SOURCES.keys())).pack(fill="x")

        buttons = ttk.Frame(panel, style="Panel.TFrame")
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, textvariable=self.play_button_var, command=self._toggle_music).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ttk.Button(buttons, textvariable=self.pause_button_var, command=self._pause_resume_music).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ttk.Button(buttons, text="Stop", command=self._stop_music).pack(side="left", expand=True, fill="x")

        ttk.Button(panel, text="Select Local File", command=self._select_local_music_file).pack(fill="x", pady=(8, 0))
        ttk.Button(panel, text="Open Source Page", command=self._open_music_source_page).pack(fill="x", pady=(6, 0))

        ttk.Label(panel, textvariable=self.current_track_var, style="Panel.TLabel").pack(anchor="w", pady=(10, 0))
        ttk.Label(panel, text="Tip: platform sources open in your browser; local files play in-app.", style="Panel.TLabel").pack(anchor="w", pady=(4, 0))

    def _build_activity_tab(self) -> None:
        self._add_custom_banner(self.activity_tab, "Activity and Logs")

        frame = ttk.LabelFrame(self.activity_tab, text="Command activity", style="Card.TLabelframe", padding=18)
        frame.pack(fill="both", expand=True, padx=18, pady=(12, 18))

        pal = self._active_palette()
        self.log = ScrolledText(
            frame,
            wrap="word",
            height=30,
            font=("Consolas", 10),
            bg=pal["input_bg"],
            fg=pal["input_fg"],
            padx=14,
            pady=14,
        )
        self.log.pack(fill="both", expand=True, padx=12, pady=12)
        self.log.insert("end", "Session started.\n")
        self.log.configure(state="disabled")

    def _build_help_tab(self) -> None:
        self._add_custom_banner(self.help_tab, "Help and Arguments")

        outer = ttk.Frame(self.help_tab, style="App.TFrame", padding=10)
        outer.pack(fill="both", expand=True)

        pal = self._active_palette()
        info = ScrolledText(outer, wrap="word", font=("Verdana", 10), bg=pal["input_bg"], fg=pal["input_fg"])
        info.pack(fill="both", expand=True)
        info.insert("end", self._help_text())
        info.configure(state="disabled")

        actions = ttk.Frame(outer, style="App.TFrame")
        actions.pack(fill="x", pady=(8, 0))
        actions.columnconfigure(0, weight=0)
        actions.columnconfigure(1, weight=1)

        ttk.Button(actions, text="Open Official yt-dlp Documentation", command=lambda: webbrowser.open(DOCS_URL)).grid(row=0, column=0, sticky="w")
        self.docs_url_label = ttk.Label(actions, text=self.docs_url_full_text, style="App.TLabel")
        self.docs_url_label.grid(row=0, column=1, sticky="ew", padx=(12, 0))

        backend = ttk.LabelFrame(outer, text="Display Backend Launch", style="Card.TLabelframe", padding=8)
        backend.pack(fill="x", pady=(8, 0))
        ttk.Label(backend, text="Use these launch commands in a terminal when forcing a backend:", style="App.TLabel").pack(anchor="w")

        button_row = ttk.Frame(backend, style="App.TFrame")
        button_row.pack(fill="x", pady=(8, 0))
        ttk.Button(button_row, text="Copy Wayland Launch", command=lambda: self._copy_backend_launch("wayland")).pack(side="left", padx=(0, 8))
        ttk.Button(button_row, text="Copy X11 Launch", command=lambda: self._copy_backend_launch("x11")).pack(side="left")

        self.backend_commands_label = ttk.Label(
            backend,
            text=self.backend_commands_full_text,
            style="App.TLabel",
            justify="left",
            anchor="w",
        )
        self.backend_commands_label.pack(anchor="w", pady=(8, 0), fill="x")

    def _build_credits_tab(self) -> None:
        self._add_custom_banner(self.credits_tab, "Credits and Sources")

        outer = ttk.Frame(self.credits_tab, style="App.TFrame", padding=10)
        outer.pack(fill="both", expand=True)

        table_box = ttk.LabelFrame(outer, text="Assets and sources", style="Card.TLabelframe", padding=8)
        table_box.pack(fill="both", expand=True)

        columns = ("asset", "source", "license")
        self.credits_tree = ttk.Treeview(table_box, columns=columns, show="headings", style="Vintage.Treeview")
        self.credits_tree.heading("asset", text="Asset / Group")
        self.credits_tree.heading("source", text="Source")
        self.credits_tree.heading("license", text="License / Terms")
        self.credits_tree.column("asset", width=260, anchor="w")
        self.credits_tree.column("source", width=500, anchor="w")
        self.credits_tree.column("license", width=260, anchor="w")
        self.credits_tree.pack(fill="both", expand=True)

        grouped_rows = [
            (
                "yt-dlp official logo",
                "https://github.com/yt-dlp/yt-dlp/blob/master/devscripts/logo.ico",
                "Project official logo",
            ),
            (
                "Music platforms",
                "Spotify / YouTube Music / SoundCloud / Deezer / Newgrounds / TIDAL / RiMusic",
                "Use each platform according to its own terms",
            ),
            (
                "Online design texture",
                f"{DESIGN_TEXTURE['name']} — {DESIGN_TEXTURE['source']}",
                DESIGN_TEXTURE["license"],
            ),
            (
                "UI motifs and layout",
                "Custom in-app canvas rendering",
                "Original project UI design",
            ),
        ]
        for row in grouped_rows:
            self.credits_tree.insert("", "end", values=row)

        self.after_idle(self._apply_responsive_text)

    def _mode_button_text(self) -> str:
        return "Disable Expert" if self.mode_var.get() else "Enable Expert"

    def _set_expert_tab_visible(self, visible: bool) -> None:
        expert_tab_id = str(self.expert_tab)
        visible_now = expert_tab_id in self.notebook.tabs()

        if visible and not visible_now:
            self.notebook.add(self.expert_tab, text="Expert")
        elif not visible and visible_now:
            if self.notebook.select() == expert_tab_id:
                self.notebook.select(self.download_tab)
            self.notebook.forget(self.expert_tab)

    def _toggle_mode(self) -> None:
        self.mode_var.set(not self.mode_var.get())
        self.mode_button.configure(text=self._mode_button_text())
        self._refresh_mode_state()
        self._refresh_visual_theme()
        if self.mode_var.get():
            self.notebook.select(self.expert_tab)
            self.status_var.set("Expert enabled")
        else:
            self.status_var.set("Expert disabled")

    def _toggle_mode_shortcut(self, _event: object) -> None:
        self._toggle_mode()

    def _toggle_ui_mode(self) -> None:
        self.barebones_ui_var.set(not self.barebones_ui_var.get())
        is_barebones = self.barebones_ui_var.get()

        self.ui_mode_label_var.set("UI: Simple" if is_barebones else "UI: Color")
        self.ui_button.configure(text=self.ui_mode_label_var.get())
        self.title_label.configure(text="yt-dlp GUI")
        self._refresh_visual_theme()

        if is_barebones:
            self.vibe_panel.grid_remove()
        else:
            self.vibe_panel.grid()

    def _refresh_mode_state(self) -> None:
        profile = self.format_mode_var.get()
        hint = FORMAT_PROFILES.get(profile, ([], ""))[1]
        self.profile_hint.configure(text=hint)

        self.custom_format_entry.configure(state="normal" if profile == "custom" else "disabled")
        self.audio_combo.configure(state="readonly" if profile == "audio" else "disabled")

        self._set_expert_tab_visible(self.mode_var.get())

        self._update_command_preview()

    def _choose_output_dir(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_dir_var.get() or str(Path.home()))
        if selected:
            self.output_dir_var.set(selected)

    def _build_command(self) -> list[str]:
        url = self.url_var.get().strip()
        if not url:
            raise ValueError("Please add a URL first.")

        command: list[str] = [
            self.ytdlp_command,
            "--newline",
            "-o",
            str(Path(self.output_dir_var.get()) / self.filename_template_var.get()),
            url,
        ]

        profile = self.format_mode_var.get()
        if profile in FORMAT_PROFILES and profile != "custom":
            command.extend(FORMAT_PROFILES[profile][0])
        elif profile == "custom" and self.custom_format_var.get().strip():
            command.extend(["-f", self.custom_format_var.get().strip()])

        if profile == "audio":
            command.extend(["--audio-format", self.audio_format_var.get()])

        if self.remux_container_var.get() != "auto":
            command.extend(["--remux-video", self.remux_container_var.get()])

        if not self.playlist_var.get():
            command.append("--no-playlist")
        if self.subtitles_var.get():
            command.extend(["--write-subs", "--write-auto-subs", "--sub-langs", "all"])
        if self.embed_metadata_var.get():
            command.append("--embed-metadata")
        if self.thumbnail_var.get():
            command.append("--write-thumbnail")
        if self.embed_thumbnail_var.get():
            command.append("--embed-thumbnail")

        if self.mode_var.get():
            if self.proxy_var.get().strip():
                command.extend(["--proxy", self.proxy_var.get().strip()])
            if self.rate_limit_var.get().strip():
                command.extend(["-r", self.rate_limit_var.get().strip()])
            if self.retries_var.get().strip():
                command.extend(["-R", self.retries_var.get().strip()])
            if self.cookies_from_browser_var.get().strip():
                command.extend(["--cookies-from-browser", self.cookies_from_browser_var.get().strip()])
            if self.user_agent_var.get().strip():
                command.extend(["--user-agent", self.user_agent_var.get().strip()])
            if self.referer_var.get().strip():
                command.extend(["--referer", self.referer_var.get().strip()])
            if self.concurrent_fragments_var.get().strip():
                command.extend(["-N", self.concurrent_fragments_var.get().strip()])
            if self.download_sections_var.get().strip():
                command.extend(["--download-sections", self.download_sections_var.get().strip()])
            if self.ignore_errors_var.get():
                command.append("--ignore-errors")
            if self.no_warnings_var.get():
                command.append("--no-warnings")
            if self.additional_args_var.get().strip():
                command.extend(shlex.split(self.additional_args_var.get().strip()))

        return command

    def _update_command_preview(self) -> None:
        try:
            self.command_preview_var.set(shlex.join(self._build_command()))
        except Exception:
            self.command_preview_var.set("Add URL to build command preview")

    def _start_download(self) -> None:
        if self.process and self.process.poll() is None:
            messagebox.showinfo("Command already running", "Stop the active command first.")
            return

        try:
            command = self._build_command()
        except ValueError as err:
            messagebox.showerror("Missing required field", str(err))
            return

        self.progress_var.set(0)
        self.status_var.set("Starting download…")
        self._append_log(f"$ {' '.join(command)}")

        try:
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=os.environ.copy(),
            )
        except FileNotFoundError:
            messagebox.showerror("yt-dlp not found", "The bundled or system yt-dlp command could not be started.")
            self.status_var.set("yt-dlp command missing")
            return
        except Exception as err:
            messagebox.showerror("Could not start command", str(err))
            self.status_var.set("Failed to start")
            return

        threading.Thread(target=self._read_process_output, daemon=True).start()

    def _list_formats(self) -> None:
        if self.process and self.process.poll() is None:
            messagebox.showinfo("Command already running", "Stop the active command first.")
            return

        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Missing URL", "Please add a URL first.")
            return

        command = [self.ytdlp_command, "-F", url]
        self.status_var.set("Listing formats in Activity tab…")
        self._append_log(f"$ {' '.join(command)}")

        try:
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=os.environ.copy(),
            )
        except Exception as err:
            messagebox.showerror("Could not list formats", str(err))
            self.status_var.set("Failed to list formats")
            return

        threading.Thread(target=self._read_process_output, daemon=True).start()

    def _stop_download(self) -> None:
        if not self.process or self.process.poll() is not None:
            self.status_var.set("No active command")
            return
        self.process.terminate()
        self.status_var.set("Stopping command…")
        self._append_log("Stop requested by user.")

    def _read_process_output(self) -> None:
        if not self.process or not self.process.stdout:
            return

        for line in self.process.stdout:
            self.output_queue.put(line.rstrip("\n"))

        code = self.process.wait()
        if code == 0:
            self.output_queue.put("__DONE__")
        else:
            self.output_queue.put(f"__ERROR__:{code}")

    def _poll_output(self) -> None:
        while True:
            try:
                line = self.output_queue.get_nowait()
            except queue.Empty:
                break

            if line == "__DONE__":
                self.status_var.set("Command completed successfully")
                self.progress_var.set(100)
                self._append_log("Command completed.")
                continue

            if line.startswith("__ERROR__"):
                code = line.split(":", 1)[1]
                self.status_var.set(f"Command failed with exit code {code}")
                self._append_log(f"Command failed (exit {code}).")
                continue

            self._append_log(line)
            match = re.search(r"(\d+(?:\.\d+)?)%", line)
            if match:
                try:
                    value = float(match.group(1))
                    self.progress_var.set(max(0, min(100, value)))
                    self.status_var.set(f"Working… {value:.1f}%")
                except ValueError:
                    pass

        self.after(120, self._poll_output)

    def _music_target(self) -> str:
        source = self.music_source_var.get().strip()
        if source == "Local File":
            return self.local_music_file_var.get().strip()
        return MUSIC_SOURCES.get(source, {}).get("stream_url", "")

    def _toggle_music(self) -> None:
        if self.music_process and self.music_process.poll() is None:
            self._stop_music()
            return
        self._start_music()

    def _start_music(self) -> None:
        source = self.music_source_var.get().strip()
        target = self._music_target()
        if not target:
            page_url = MUSIC_SOURCES.get(source, {}).get("page_url", "")
            if page_url:
                webbrowser.open(page_url)
                self.current_track_var.set(f"Current track: {source}")
                self.status_var.set(f"Opened {source} in browser")
                return
            messagebox.showerror("No music source", "Choose an online source or local file first.")
            return

        player_command: list[str] | None = None
        if shutil.which("mpv"):
            player_command = ["mpv", "--no-video", "--force-window=no", "--really-quiet", target]
        elif shutil.which("ffplay"):
            player_command = ["ffplay", "-nodisp", "-loglevel", "error", "-nostats", target]
        elif shutil.which("mpg123"):
            player_command = ["mpg123", "-q", target]

        if not player_command:
            messagebox.showerror("No audio player found", "Install mpv, ffplay, or mpg123 to use music playback.")
            return

        try:
            self.music_process = subprocess.Popen(
                player_command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=os.environ.copy(),
            )
            self.music_paused = False
            self.play_button_var.set("Stop")
            self.pause_button_var.set("Pause")
            self.status_var.set("Music started")
            self._append_log(f"$ {' '.join(player_command)}")
            self._start_now_playing_loop()
        except Exception as err:
            messagebox.showerror("Could not start music", str(err))

    def _pause_resume_music(self) -> None:
        if not self.music_process or self.music_process.poll() is not None:
            return
        try:
            if self.music_paused:
                self.music_process.send_signal(signal.SIGCONT)
                self.music_paused = False
                self.pause_button_var.set("Pause")
                self.status_var.set("Music resumed")
            else:
                self.music_process.send_signal(signal.SIGSTOP)
                self.music_paused = True
                self.pause_button_var.set("Resume")
                self.status_var.set("Music paused")
        except Exception:
            pass

    def _stop_music(self) -> None:
        if self.music_process and self.music_process.poll() is None:
            self.music_process.terminate()
        self.music_process = None
        self.music_paused = False
        self.play_button_var.set("Play")
        self.pause_button_var.set("Pause")
        self.current_track_var.set("Current track: idle")
        self.status_var.set("Music stopped")

    def _select_local_music_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Select local audio file",
            filetypes=[("Audio files", "*.mp3 *.flac *.wav *.ogg *.m4a *.opus"), ("All files", "*.*")],
        )
        if not path:
            return
        self.local_music_file_var.set(path)
        self.music_source_var.set("Local File")
        self.current_track_var.set(f"Current track: {Path(path).name}")

    def _open_music_source_page(self) -> None:
        source = self.music_source_var.get().strip()
        page = MUSIC_SOURCES.get(source, {}).get("page_url", "")
        if page:
            webbrowser.open(page)

    def _copy_backend_launch(self, backend: str) -> None:
        commands = {
            "wayland": "GDK_BACKEND=wayland QT_QPA_PLATFORM=wayland SDL_VIDEODRIVER=wayland XDG_SESSION_TYPE=wayland yt-dlp-gui",
            "x11": "GDK_BACKEND=x11 QT_QPA_PLATFORM=xcb SDL_VIDEODRIVER=x11 XDG_SESSION_TYPE=x11 yt-dlp-gui",
        }
        command = commands.get(backend, "")
        if not command:
            return
        self.clipboard_clear()
        self.clipboard_append(command)
        self.status_var.set(f"Copied {backend.upper()} launch command")

    def _start_now_playing_loop(self) -> None:
        if self.music_polling:
            return
        self.music_polling = True
        threading.Thread(target=self._poll_now_playing_worker, daemon=True).start()

    def _poll_now_playing_worker(self) -> None:
        while self.music_process and self.music_process.poll() is None:
            try:
                source = self.music_source_var.get().strip()
                if source == "Local File":
                    name = Path(self.local_music_file_var.get()).name if self.local_music_file_var.get() else "Local file"
                    self.current_track_var.set(f"Current track: {name}")
                else:
                    page = MUSIC_SOURCES.get(source, {}).get("now_playing", "")
                    track = self._fetch_now_playing_from_page(page)
                    if track:
                        self.current_track_var.set(f"Current track: {track}")
                    else:
                        self.current_track_var.set(f"Current track: {source}")
            except Exception:
                pass
            time.sleep(12)
        self.music_polling = False

    def _fetch_now_playing_from_page(self, page_url: str) -> str:
        if not page_url:
            return ""
        req = urllib.request.Request(page_url, headers={"User-Agent": "yt-dlp-gui"})
        with urllib.request.urlopen(req, timeout=8) as response:
            html = response.read().decode("utf-8", errors="ignore")
        match = re.search(r"Now Playing:\s*([^<\n]+)", html, flags=re.IGNORECASE)
        return match.group(1).strip() if match else ""

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.insert("end", "Session started.\n")
        self.log.configure(state="disabled")

    def _copy_command_preview(self) -> None:
        text = self.command_preview_var.get().strip()
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_var.set("Command copied to clipboard")

    def _load_current_version(self) -> None:
        try:
            result = subprocess.run([self.ytdlp_command, "--version"], capture_output=True, text=True, check=True)
            self.current_version_full_text = f"Installed yt-dlp: {result.stdout.strip()}"
        except Exception:
            self.current_version_full_text = "Installed yt-dlp: unavailable"
        self._apply_responsive_text()

    def _installed_version(self) -> str | None:
        try:
            result = subprocess.run([self.ytdlp_command, "--version"], capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except Exception:
            return None

    def _version_tuple(self, version: str) -> tuple[int, ...]:
        numbers = re.findall(r"\d+", version)
        return tuple(int(n) for n in numbers) if numbers else (0,)

    def _check_updates_thread(self) -> None:
        threading.Thread(target=self._check_updates, daemon=True).start()

    def _check_updates(self) -> None:
        self.status_var.set("Checking latest stable release…")
        try:
            req = urllib.request.Request(
                RELEASE_API_URL,
                headers={"Accept": "application/vnd.github+json", "User-Agent": "yt-dlp-gui"},
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))

            latest = str(payload.get("tag_name", "")).strip()
            if not latest:
                raise RuntimeError("Release API did not include tag_name")

            self.latest_stable_version = latest
            current = self._installed_version()

            if current and self._version_tuple(latest) > self._version_tuple(current):
                self.latest_version_full_text = f"Latest stable release: {latest} (update available)"
                self.status_var.set("New stable yt-dlp release detected")
                self._append_log(f"Update available: installed={current}, latest={latest}")
            elif current:
                self.latest_version_full_text = f"Latest stable release: {latest} (up to date)"
                self.status_var.set("yt-dlp is already up to date")
                self._append_log(f"No update needed: installed={current}, latest={latest}")
            else:
                self.latest_version_full_text = f"Latest stable release: {latest}"
                self.status_var.set("Could not detect local version")

            self._apply_responsive_text()

        except urllib.error.URLError as err:
            self.status_var.set("Could not contact GitHub release API")
            messagebox.showerror("Update check failed", f"Could not reach GitHub API.\n\n{err}")
        except Exception as err:
            self.status_var.set("Update check failed")
            messagebox.showerror("Update check failed", str(err))

    def _run_update_flow(self) -> None:
        if not self.latest_stable_version:
            self._check_updates_thread()
            self._debug_log("Update started without cached latest version; check scheduled in background")

        if not messagebox.askyesno(
            "Update yt-dlp",
            "This will update the bundled yt-dlp executable.\n\n"
            "If elevated privileges are required, it will use pkexec when available.\n"
            "If unavailable, it falls back to available system update methods.\n\n"
            "Continue?",
        ):
            return

        threading.Thread(target=self._perform_update, daemon=True).start()

    def _perform_update(self) -> None:
        self.status_var.set("Running update command…")

        pacman = shutil.which("pacman")
        pkexec = shutil.which("pkexec")
        bundled_self_update = [self.ytdlp_command, "-U"]

        commands: list[list[str]] = []
        if self._is_writable_executable(self.ytdlp_command):
            commands.append(bundled_self_update)
        elif pkexec:
            commands.append([pkexec, *bundled_self_update])

        if pacman and pkexec:
            commands.append([pkexec, pacman, "-S", "--needed", "--noconfirm", "yt-dlp"])
        if pacman:
            commands.append([pacman, "-S", "--needed", "--noconfirm", "yt-dlp"])

        if bundled_self_update not in commands:
            commands.append(bundled_self_update)

        self._debug_log(f"Updater started. pacman={bool(pacman)} pkexec={bool(pkexec)}")

        last_error: Exception | None = None
        for command in commands:
            self._append_log(f"$ {' '.join(command)}")
            self._debug_log(f"Trying update command: {' '.join(command)}")
            try:
                proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=os.environ.copy())
                if proc.stdout:
                    for line in proc.stdout:
                        self.output_queue.put(line.rstrip("\n"))
                code = proc.wait()
                if code == 0:
                    self.status_var.set("yt-dlp update completed")
                    self._debug_log(f"Update command succeeded: {' '.join(command)}")
                    self._load_current_version()
                    self._check_updates()
                    return
                last_error = RuntimeError(f"Command exited with code {code}")
                self._debug_log(f"Update command failed ({code}): {' '.join(command)}")
            except Exception as err:
                last_error = err
                self._debug_log(f"Update command exception: {err}")

        self.status_var.set("yt-dlp update failed")
        error_text = str(last_error) if last_error else "Unknown error"
        if self.stacktrace_dialogs_var.get() and last_error:
            error_text = f"{error_text}\n\nSee debug log: {self.debug_log_path}\nCrash log: {self.crash_log_path}"
        messagebox.showerror("Update failed", error_text)

    def _show_about(self) -> None:
        messagebox.showinfo(
            "About yt-dlp GUI",
            f"yt-dlp GUI v{__version__}\n\n"
            "Custom-styled desktop interface for yt-dlp with integrated music controls.",
        )

    def _help_text(self) -> str:
        return (
            "yt-dlp GUI Help\n"
            "================\n\n"
            "This app provides a desktop interface for yt-dlp.\n\n"
            "Visual Modes\n"
            "------------\n"
            "- Color mode (default): structured interface with visual accents.\n"
            "- Simple mode: minimal styling focused on core controls.\n"
            "- Toggle using the header button or View menu.\n\n"
            "Simple vs Expert\n"
            "----------------\n"
            "- Simple mode shows the essential download controls.\n"
            "- Expert mode exposes advanced network and yt-dlp argument controls.\n"
            "- Press Ctrl+M to toggle quickly.\n\n"
            "Music\n"
            "-----\n"
            "- Supports major platform shortcuts and local audio files.\n"
            "- Platform sources open in browser; local files can play in-app.\n"
            "- Includes Play, Pause/Resume, and Stop controls.\n"
            "- Shows current source or local file title.\n\n"
            "Display Backend\n"
            "---------------\n"
            "- The header shows the current backend detected from your session.\n"
            "- Help tab includes buttons to copy launch commands for Wayland or X11.\n\n"
            "Arguments and Flags\n"
            "-------------------\n"
            "- -f <selector>: choose stream format expression\n"
            "- -x: extract audio\n"
            "- --audio-format <fmt>: set output audio format\n"
            "- --remux-video <container>: remux container\n"
            "- -o <template>: output path/template\n"
            "- --no-playlist: single target download\n"
            "- --write-subs / --write-auto-subs: subtitle options\n"
            "- --sub-langs all: all subtitle languages\n"
            "- --embed-metadata: write media metadata\n"
            "- --write-thumbnail / --embed-thumbnail: thumbnail handling\n"
            "- --proxy <url>: proxy route\n"
            "- -r <rate>: rate limit\n"
            "- -R <count>: retry count\n"
            "- --cookies-from-browser <name>: import auth cookies\n"
            "- --user-agent <value>: override HTTP user-agent\n"
            "- --referer <url>: set HTTP referer\n"
            "- -N <count>: concurrent fragment downloads\n"
            "- --download-sections <spec>: download specific media sections\n"
            "- --ignore-errors: continue on extraction/download errors\n"
            "- --no-warnings: suppress warning output\n"
            "- Additional raw args: append any extra yt-dlp flags in Expert mode\n\n"
            "Official docs\n"
            "-------------\n"
            f"{DOCS_URL}\n"
        )

    def _on_close(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
        self._stop_music()
        self._save_user_settings()
        self.destroy()


def main() -> None:
    cache_root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    crash_dir = cache_root / "yt-dlp-gui"
    crash_log = crash_dir / "crash.log"

    def _write_startup_log(err: BaseException) -> None:
        crash_dir.mkdir(parents=True, exist_ok=True)
        crash_log.write_text(traceback.format_exc(), encoding="utf-8")
        print(f"yt-dlp-gui failed to start: {err}", flush=True)
        print(f"Crash log written to: {crash_log}", flush=True)

    try:
        app = YtDlpGui()
        app.mainloop()
    except TclError as err:
        message = str(err)
        _write_startup_log(err)
        if "no display name" in message or "$DISPLAY" in message:
            print("yt-dlp-gui needs a graphical session (X11 via XWayland or native X11).", flush=True)
            return
        raise
    except Exception as err:
        _write_startup_log(err)

        try:
            recovery = Tk(className="yt-dlp-gui")
            recovery.title("yt-dlp GUI recovery")
            recovery.geometry("760x240")

            frame = ttk.Frame(recovery, padding=12)
            frame.pack(fill="both", expand=True)

            ttk.Label(frame, text="yt-dlp-gui failed to start fully.", font=("Verdana", 11, "bold")).pack(anchor="w")
            ttk.Label(frame, text=f"Error: {err}", wraplength=720).pack(anchor="w", pady=(8, 8))
            ttk.Label(frame, text=f"Crash log: {crash_log}", wraplength=720).pack(anchor="w", pady=(0, 10))

            ttk.Button(frame, text="Open crash log", command=lambda: webbrowser.open(crash_log.as_uri())).pack(anchor="w")
            recovery.mainloop()
        except Exception:
            print(f"yt-dlp-gui failed to start: {err}", flush=True)
            print(f"Crash log written to: {crash_log}", flush=True)


if __name__ == "__main__":
    main()
