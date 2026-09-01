from __future__ import annotations

from pathlib import Path
import os
import platform
import queue
import sys
import threading
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .command import display_command, run_command
from .config import SetupOptions, redacted_env_preview
from .orchestrator import SetupFailure, SetupResult, perform_setup
from .platform_install import install_plan
from .preflight import Check, run_preflight


APP_TITLE = "LLM Framework Setup"


def _initial_project_root() -> Path:
    candidates = [Path.cwd()]
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        candidates.extend(list(executable.parents)[:6])
    else:
        candidates.append(Path(__file__).resolve().parents[2])
    for candidate in candidates:
        if (candidate / "docker-compose.yml").is_file():
            return candidate
    return Path.cwd()


class SetupApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.last_result: SetupResult | None = None
        self.busy = False

        root.title(APP_TITLE)
        root.geometry("1000x720")
        root.minsize(760, 620)
        root.option_add("*Font", ("TkDefaultFont", 11))
        self._configure_style()

        self.project_var = tk.StringVar(value=str(_initial_project_root()))
        default_mode = "native" if platform.system() in {"Darwin", "Windows"} else "bundled"
        self.mode_var = tk.StringVar(value=default_mode)
        self.endpoint_var = tk.StringVar()
        self.chat_model_var = tk.StringVar(value="qwen2.5-coder:7b")
        self.embedding_model_var = tk.StringVar(value="nomic-embed-text")
        self.replace_var = tk.BooleanVar(value=False)
        self.stage_var = tk.StringVar(value="Run the system check to begin.")

        self._build()
        self._update_endpoint()
        self.root.after(120, self._drain_events)
        self.root.after(250, self.refresh_checks)

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        if platform.system() != "Darwin":
            try:
                style.theme_use("clam")
            except tk.TclError:
                pass
        style.configure("Title.TLabel", font=("TkDefaultFont", 20, "bold"))
        style.configure("Section.TLabel", font=("TkDefaultFont", 13, "bold"))
        style.configure("Primary.TButton", font=("TkDefaultFont", 11, "bold"), padding=(16, 10))

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=20)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="Set up LLM Framework", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text=(
                "Checks this computer, guides prerequisite installation, creates local secrets, "
                "starts the framework, and verifies it before declaring success."
            ),
            wraplength=940,
        ).pack(anchor="w", pady=(4, 16))

        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)
        checks_tab = ttk.Frame(notebook, padding=14)
        install_tab = ttk.Frame(notebook, padding=14)
        progress_tab = ttk.Frame(notebook, padding=14)
        notebook.add(checks_tab, text="1. System check")
        notebook.add(install_tab, text="2. Configure and install")
        notebook.add(progress_tab, text="3. Progress")
        self.notebook = notebook

        self._build_checks(checks_tab)
        self._build_install(install_tab)
        self._build_progress(progress_tab)

    def _build_checks(self, parent: ttk.Frame) -> None:
        folder = ttk.Frame(parent)
        folder.pack(fill="x", pady=(0, 10))
        ttk.Label(folder, text="Repository folder:").pack(side="left")
        ttk.Entry(folder, textvariable=self.project_var).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(folder, text="Browse…", command=self.choose_folder).pack(side="left")

        columns = ("status", "check", "detail", "action")
        tree = ttk.Treeview(parent, columns=columns, show="headings", height=13)
        tree.heading("status", text="Status")
        tree.heading("check", text="Check")
        tree.heading("detail", text="What was found")
        tree.heading("action", text="Next action")
        tree.column("status", width=90, stretch=False)
        tree.column("check", width=150, stretch=False)
        tree.column("detail", width=310)
        tree.column("action", width=330)
        tree.pack(fill="both", expand=True)
        self.check_tree = tree

        actions = ttk.Frame(parent)
        actions.pack(fill="x", pady=(12, 0))
        self.recheck_button = ttk.Button(actions, text="Run checks again", command=self.refresh_checks)
        self.recheck_button.pack(side="left")
        ttk.Button(actions, text="Install Docker…", command=lambda: self.install_dependency("docker")).pack(side="left", padx=8)
        ttk.Button(actions, text="Install Ollama…", command=lambda: self.install_dependency("ollama")).pack(side="left")
        ttk.Label(
            parent,
            text="Docker images include PostgreSQL, Python, Node.js, and application packages; they do not need separate host installation.",
            wraplength=920,
        ).pack(anchor="w", pady=(12, 0))

    def _build_install(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Ollama location", style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        modes = (
            ("native", "Installed on this computer (recommended for macOS/Windows GPU support)"),
            ("bundled", "Included in Docker (portable; base configuration may be CPU-only)"),
            ("remote", "Another computer or endpoint (advanced)"),
        )
        for index, (value, label) in enumerate(modes, start=1):
            ttk.Radiobutton(parent, text=label, value=value, variable=self.mode_var, command=self._update_endpoint).grid(
                row=index, column=0, columnspan=3, sticky="w", pady=3
            )

        ttk.Label(parent, text="Ollama endpoint:").grid(row=4, column=0, sticky="w", pady=(12, 4))
        self.endpoint_entry = ttk.Entry(parent, textvariable=self.endpoint_var, width=70)
        self.endpoint_entry.grid(row=4, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=(12, 4))

        ttk.Separator(parent).grid(row=5, column=0, columnspan=3, sticky="ew", pady=16)
        ttk.Label(parent, text="Models", style="Section.TLabel").grid(row=6, column=0, columnspan=3, sticky="w")
        ttk.Label(parent, text="Chat model:").grid(row=7, column=0, sticky="w", pady=6)
        ttk.Entry(parent, textvariable=self.chat_model_var, width=38).grid(row=7, column=1, sticky="w", padx=(8, 0))
        ttk.Label(parent, text="Embedding model:").grid(row=8, column=0, sticky="w", pady=6)
        ttk.Entry(parent, textvariable=self.embedding_model_var, width=38).grid(row=8, column=1, sticky="w", padx=(8, 0))
        ttk.Label(
            parent,
            text="Model downloads can be several gigabytes. Remote mode verifies the endpoint but does not install models on that computer.",
            wraplength=880,
        ).grid(row=9, column=0, columnspan=3, sticky="w", pady=(4, 12))

        ttk.Separator(parent).grid(row=10, column=0, columnspan=3, sticky="ew", pady=12)
        ttk.Label(parent, text="Existing installation", style="Section.TLabel").grid(row=11, column=0, columnspan=3, sticky="w")
        ttk.Checkbutton(
            parent,
            text="Replace the existing .env after making a timestamped backup",
            variable=self.replace_var,
        ).grid(row=12, column=0, columnspan=2, sticky="w", pady=8)
        ttk.Button(parent, text="Preview existing configuration", command=self.preview_configuration).grid(row=12, column=2, sticky="e")

        review = (
            "The launcher generates database and access secrets locally. It never logs or uploads them. "
            "Prompts and framework data remain local unless you deliberately configure a remote model endpoint."
        )
        ttk.Label(parent, text=review, wraplength=900).grid(row=13, column=0, columnspan=3, sticky="w", pady=(12, 16))
        self.install_button = ttk.Button(parent, text="Install and start framework", style="Primary.TButton", command=self.start_setup)
        self.install_button.grid(row=14, column=0, columnspan=3, sticky="w")
        parent.columnconfigure(1, weight=1)

    def _build_progress(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, textvariable=self.stage_var, style="Section.TLabel", wraplength=920).pack(anchor="w", pady=(0, 10))
        progress = ttk.Progressbar(parent, mode="indeterminate")
        progress.pack(fill="x", pady=(0, 12))
        self.progress = progress
        log = tk.Text(parent, height=20, wrap="word", state="disabled")
        log.pack(fill="both", expand=True)
        self.log = log
        buttons = ttk.Frame(parent)
        buttons.pack(fill="x", pady=(12, 0))
        self.open_button = ttk.Button(buttons, text="Open framework", command=self.open_framework, state="disabled")
        self.open_button.pack(side="left")
        self.copy_button = ttk.Button(buttons, text="Copy recovery access token", command=self.copy_token, state="disabled")
        self.copy_button.pack(side="left", padx=8)

    def choose_folder(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.project_var.get(), title="Choose the extracted LLM Framework folder")
        if chosen:
            self.project_var.set(chosen)
            self.refresh_checks()

    def _update_endpoint(self) -> None:
        mode = self.mode_var.get()
        if mode == "native":
            self.endpoint_var.set("http://host.docker.internal:11434")
            self.endpoint_entry.configure(state="disabled")
        elif mode == "bundled":
            self.endpoint_var.set("http://ollama:11434")
            self.endpoint_entry.configure(state="disabled")
        else:
            if self.endpoint_var.get() in {"http://host.docker.internal:11434", "http://ollama:11434"}:
                self.endpoint_var.set("http://")
            self.endpoint_entry.configure(state="normal")

    def refresh_checks(self) -> None:
        if self.busy:
            return
        self.busy = True
        self.recheck_button.configure(state="disabled")
        self.stage_var.set("Checking this computer…")

        def worker() -> None:
            try:
                checks = run_preflight(Path(self.project_var.get()).expanduser())
                self.events.put(("checks", checks))
            except Exception as exc:  # noqa: BLE001 - surfaced in the local GUI
                self.events.put(("error", f"System check failed: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def install_dependency(self, dependency: str) -> None:
        plan = install_plan(dependency)
        if plan.command is None:
            messagebox.showinfo(
                f"Install {dependency.title()}",
                plan.explanation + "\n\nThe official installation page will now open.",
            )
            webbrowser.open(plan.official_url)
            return
        command = display_command(plan.command)
        approved = messagebox.askyesno(
            f"Install {dependency.title()}",
            f"{plan.explanation}\n\nThe launcher will run exactly:\n\n{command}\n\nContinue?",
        )
        if not approved:
            return
        self.busy = True
        self.stage_var.set(f"Installing {dependency}…")
        self.notebook.select(2)
        self.progress.start(12)
        self._append_log(f"Installing {dependency} with {plan.method}. Administrator confirmation may appear.")

        def worker() -> None:
            result = run_command(plan.command or (), timeout=1800)
            self.events.put(("dependency", (dependency, plan, result)))

        threading.Thread(target=worker, daemon=True).start()

    def preview_configuration(self) -> None:
        path = Path(self.project_var.get()).expanduser() / ".env"
        try:
            preview = redacted_env_preview(path)
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"Could not read configuration: {exc}")
            return
        window = tk.Toplevel(self.root)
        window.title("Redacted configuration preview")
        window.geometry("760x460")
        text = tk.Text(window, wrap="none")
        text.insert("1.0", preview)
        text.configure(state="disabled")
        text.pack(fill="both", expand=True, padx=12, pady=12)

    def start_setup(self) -> None:
        if self.busy:
            return
        project = Path(self.project_var.get()).expanduser()
        env_exists = (project / ".env").exists()
        if env_exists and self.replace_var.get():
            if not messagebox.askyesno(
                "Replace configuration?",
                "The existing .env will be copied to a timestamped backup and replaced with new local secrets. Continue?",
            ):
                return
        elif env_exists:
            if not messagebox.askyesno(
                "Reuse existing configuration?",
                "The existing .env will be preserved. Its Ollama endpoint controls which services are used. Continue?",
            ):
                return

        options = SetupOptions(
            project_root=project,
            ollama_mode=self.mode_var.get(),
            ollama_endpoint=self.endpoint_var.get(),
            chat_model=self.chat_model_var.get(),
            embedding_model=self.embedding_model_var.get(),
            replace_existing=self.replace_var.get(),
        )
        self.last_result = None
        self.busy = True
        self.install_button.configure(state="disabled")
        self.open_button.configure(state="disabled")
        self.copy_button.configure(state="disabled")
        self.progress.start(12)
        self.notebook.select(2)
        self._append_log("Setup started. Completed downloads and containers are preserved if a later stage fails.")

        def callback(stage: str, detail: str) -> None:
            self.events.put(("stage", (stage, detail)))

        def worker() -> None:
            try:
                result = perform_setup(options, callback)
                self.events.put(("success", result))
            except SetupFailure as exc:
                self.events.put(("setup-failure", exc))
            except Exception as exc:  # noqa: BLE001 - surfaced without secrets or raw command output
                self.events.put(("error", f"Setup stopped safely: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def _append_log(self, line: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", line.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_idle(self) -> None:
        self.busy = False
        self.progress.stop()
        self.recheck_button.configure(state="normal")
        self.install_button.configure(state="normal")

    def _drain_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "checks":
                    self.check_tree.delete(*self.check_tree.get_children())
                    for check in payload:  # type: ignore[union-attr]
                        item: Check = check
                        label = {"ready": "Ready", "warning": "Review", "missing": "Missing"}.get(item.status, item.status)
                        self.check_tree.insert("", "end", values=(label, item.label, item.detail, item.action))
                    self.stage_var.set("System check complete. Review missing items before installation.")
                    self._set_idle()
                elif event == "stage":
                    stage, detail = payload  # type: ignore[misc]
                    self.stage_var.set(detail)
                    self._append_log(f"[{stage}] {detail}")
                elif event == "dependency":
                    dependency, plan, result = payload  # type: ignore[misc]
                    self._set_idle()
                    if result.ok:
                        self.stage_var.set(f"{dependency.title()} installation command completed.")
                        self._append_log(f"{dependency.title()} installation completed. Start the application if required, then run checks again.")
                        messagebox.showinfo(APP_TITLE, f"{dependency.title()} installed. Start it if required, then run the system check again.")
                    else:
                        self.stage_var.set(f"{dependency.title()} installation did not complete.")
                        self._append_log(f"Installation failed or timed out. Use the official instructions: {plan.official_url}")
                        if messagebox.askyesno(APP_TITLE, "Installation did not complete. Open the official instructions?"):
                            webbrowser.open(plan.official_url)
                elif event == "success":
                    result: SetupResult = payload  # type: ignore[assignment]
                    self.last_result = result
                    self._set_idle()
                    self.stage_var.set("Setup complete. Backend and frontend health checks passed.")
                    self._append_log("[complete] Framework is ready at http://localhost:3000.")
                    self.open_button.configure(state="normal")
                    self.copy_button.configure(state="normal")
                    messagebox.showinfo(APP_TITLE, "LLM Framework is installed, running, and verified.")
                elif event == "setup-failure":
                    failure: SetupFailure = payload  # type: ignore[assignment]
                    self._set_idle()
                    self.stage_var.set(f"Stopped during {failure.stage}: {failure}")
                    self._append_log(f"[{failure.stage}] {failure}\nNext action: {failure.action}")
                    messagebox.showerror(APP_TITLE, f"{failure}\n\nNext action:\n{failure.action}")
                elif event == "error":
                    self._set_idle()
                    self.stage_var.set(str(payload))
                    self._append_log(str(payload))
                    messagebox.showerror(APP_TITLE, str(payload))
        except queue.Empty:
            pass
        self.root.after(120, self._drain_events)

    def open_framework(self) -> None:
        if self.last_result:
            webbrowser.open(self.last_result.frontend_url)

    def copy_token(self) -> None:
        if not self.last_result:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.last_result.configuration.access_token)
        self.root.update()
        messagebox.showinfo(APP_TITLE, "Recovery access token copied. Store it securely and clear your clipboard afterward.")


def run_app() -> None:
    if platform.system() == "Linux" and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        raise SystemExit("A graphical desktop session is required. See setup_launcher/README.md for manual setup.")
    root = tk.Tk()
    SetupApp(root)
    root.mainloop()
