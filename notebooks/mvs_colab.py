"""MVS Colab runner. Used verbatim in the shipped notebook; no Google credentials required.

The optional browser-to-desktop connection is loopback-only. It requires the user's
browser permission. Manual job upload/result import remains supported when blocked.
"""
from __future__ import annotations
import base64
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import queue
import re
import shlex
import shutil
import socket
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import uuid
import zipfile

REVISION = "ui-colab-1"
APP_VERSION = "1.4.0"
ENGINE_VERSION = "1.6.0"
FORMULA_HASH = "10a1e72218bd65ec024fc981aab9b9d0a9de8ac00db9188f9d80d54e1170598c"


def ci(obj, key, default=None):
    return next((v for k, v in obj.items() if k.lower() == key.lower()), default)


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def strict_json(path):
    def invalid(value):
        raise ValueError("Non-finite JSON token: " + value)
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), parse_constant=invalid)


def safe_extract(archive, destination, max_bytes=256 * 1024 * 1024):
    destination = Path(destination).resolve()
    with zipfile.ZipFile(archive) as z:
        total = 0
        if len(z.infolist()) > 5000:
            raise ValueError("Too many files in archive")
        for item in z.infolist():
            relative = Path(item.filename)
            if "\\" in item.filename or ":" in item.filename or relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Unsafe archive member")
            if (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Archive symlinks are not allowed")
            total += item.file_size
            if total > max_bytes:
                raise ValueError("Uncompressed archive is too large")
        destination.mkdir(parents=True, exist_ok=True)
        z.extractall(destination)


def dotnet_environment(dotnet):
    dotnet = Path(dotnet).resolve()
    env = os.environ.copy()
    env["DOTNET_ROOT"] = str(dotnet.parent)
    env["DOTNET_ROOT_X64"] = str(dotnet.parent)
    env["PATH"] = str(dotnet.parent) + os.pathsep + env.get("PATH", "")
    env["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1"
    env["DOTNET_NOLOGO"] = "1"
    return env


def cli_command(dotnet, dll, *arguments):
    # Always execute mvs.dll through the explicit host. Never rely on an apphost
    # discovering a non-system SDK installation: that caused exit 131/libhostfxr.
    return [str(Path(dotnet).resolve()), str(Path(dll).resolve()), *map(str, arguments)]


def validate_calibration(path, plan):
    try:
        state = strict_json(path)
        if ci(state, "SchemaVersion") != 2 or ci(state, "AppVersion") != APP_VERSION or ci(state, "EngineVersion") != ENGINE_VERSION:
            return False
        if ci(state, "FormulaHash") != FORMULA_HASH or ci(state, "DatasetHash") != ci(plan, "DatasetHash"):
            return False
        if ci(state, "Repetitions") != ci(plan, "Repetitions"):
            return False
        expected = ci(plan, "SettingsHash", "")
        if expected and ci(state, "SettingsHash") != expected:
            return False
        rows = ci(state, "Rows", [])
        return len(rows) == 12 and bool(ci(state, "PayloadHash")) and bool(ci(state, "SettingsHash"))
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def output_path(folder, name):
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        raise ValueError("Unsafe manifest path")
    parts = PurePosixPath(name)
    if parts.is_absolute() or ".." in parts.parts or "." == name:
        raise ValueError("Unsafe manifest path")
    path = (Path(folder) / name).resolve()
    if not path.is_relative_to(Path(folder).resolve()):
        raise ValueError("Manifest path escaped its run folder")
    return path


def validate_manifest(folder, dataset_hash=None, settings_hash=None):
    folder = Path(folder)
    benchmark = not (folder / "run_manifest.json").exists()
    manifest = strict_json(folder / ("benchmark_manifest.json" if benchmark else "run_manifest.json"))
    entries = ci(manifest, "files", [])
    if not isinstance(entries, list):
        raise ValueError("Invalid manifest file list")
    if benchmark:
        sums = folder / "SHA256SUMS.txt"
        if not sums.exists():
            raise ValueError("Benchmark checksum file is missing")
        checked = set()
        for line in sums.read_text().splitlines():
            if not line.strip():
                continue
            digest, name = line.split(maxsplit=1)
            name = name.lstrip(" *")
            if not re.fullmatch("[0-9a-f]{64}", digest) or sha(output_path(folder, name)) != digest:
                raise ValueError("Benchmark file checksum mismatch")
            checked.add(name)
        for name in entries:
            if name not in checked or not output_path(folder, name).is_file():
                raise ValueError("Benchmark output is not covered by checksums")
        if "benchmark_manifest.json" not in checked:
            raise ValueError("Benchmark manifest itself must have a checksum")
    else:
        for entry in entries:
            name = ci(entry, "fileName", "")
            path = output_path(folder, name)
            if sha(path) != ci(entry, "sha256"):
                raise ValueError("A result does not match its manifest: " + name)
        if dataset_hash:
            actual = ci(ci(manifest, "data", {}), "sha256") or ci(ci(manifest, "inputData", {}), "sha256")
            if actual != dataset_hash:
                raise ValueError("Result manifest belongs to different input data")
        if settings_hash and ci(ci(manifest, "calibration", {}), "settingsHash") != settings_hash:
            raise ValueError("Result manifest belongs to different calibration settings")
    return manifest


def find_run_folder(root):
    root = Path(root)
    candidates = sorted(list(root.rglob("run_manifest.json")) + list(root.rglob("benchmark_manifest.json")))
    if not candidates:
        return None
    # The parent is unique for ordinary workflow runs. If several completed retries exist,
    # prefer the most recently written manifest; every selected file is still verified.
    return max(candidates, key=lambda p: p.stat().st_mtime_ns).parent


def notebook_url():
    """Best effort only. Colab's browser/kernel APIs can change; a manual URL is allowed."""
    candidates = [os.environ.get("COLAB_JUPYTER_IP", ""), "172.28.0.12", "172.28.0.2", "127.0.0.1"]
    for host in dict.fromkeys(filter(None, candidates)):
        # These are only runtime-local Jupyter session lookups, not arbitrary URLs.
        if not re.fullmatch(r"(?:127\.0\.0\.1|172\.28\.0\.\d{1,3})", host):
            continue
        try:
            with urllib.request.urlopen("http" + "://" + host + ":9000/api/sessions", timeout=1) as response:
                sessions = json.load(response)
            for session in sessions:
                path = str(session.get("path", ""))
                match = re.search(r"(?:fileId=|/drive/)([A-Za-z0-9_-]{10,})", path)
                if match:
                    return "https://colab.research.google.com/drive/" + match.group(1)
        except Exception:
            pass
    return ""


def browser_request(base, route, packet=None):
    from google.colab import output
    if not re.fullmatch(r"http://127\.0\.0\.1:\d{1,5}/v1/[0-9a-f]{64}", base):
        raise ValueError("Invalid MVS connection code")
    payload = json.dumps(packet, separators=(",", ":")) if packet is not None else None
    script = """(async () => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 6000);
      try {
        const response = await fetch(URL, {method: METHOD, headers: HEADERS, body: BODY,
          credentials: 'omit', cache: 'no-store', signal: controller.signal});
        if (!response.ok) throw new Error('MVS rejected the request (' + response.status + ')');
        return {ok: true, value: await response.json()};
      } catch (error) { return {ok: false, error: String(error)}; }
      finally { clearTimeout(timer); }
    })()"""
    script = script.replace("URL", json.dumps(base + "/" + route)).replace("METHOD", json.dumps("POST" if packet is not None else "GET"))
    script = script.replace("HEADERS", json.dumps({"Content-Type": "application/json"} if packet is not None else {})).replace("BODY", json.dumps(payload) if payload is not None else "undefined")
    reply = output.eval_js(script)
    if not reply or not reply.get("ok"):
        raise ConnectionError((reply or {}).get("error", "Browser connection unavailable"))
    return reply["value"]


class Workspace:
    def __init__(self, root="/content/mvs-work", connection="", manual_job="", ref="main", mode="standard"):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.connection = connection.strip()
        self.manual_job = manual_job
        self.ref = ref
        self.mode = mode
        self.epoch = uuid.uuid4().hex
        self.url = notebook_url()
        self.phase = "ready"
        self.last_notice = ""
        self.plan = {}
        self.folder = None
        self.dotnet = None
        self.dll = None

    def activate(self):
        if self.connection:
            response = browser_request(self.connection, "job")
            archive_bytes = base64.b64decode(response["archive"], validate=True)
            if len(archive_bytes) > 100 * 1024 * 1024:
                raise ValueError("Job transfer is too large; use manual upload")
        elif self.mode in {"benchmark", "estimation"} and not self.manual_job:
            arguments = ["--profile", "quick", "--threads", "2"] if self.mode == "benchmark" else []
            key = hashlib.sha256((self.mode + REVISION + json.dumps(arguments)).encode()).hexdigest()
            plan = {"Key": key, "Kind": self.mode, "DatasetHash": "synthetic", "SettingsHash": "", "Repetitions": 2000,
                    "Arguments": arguments, "RequestedAction": "analyze"}
            memory = io.BytesIO()
            with zipfile.ZipFile(memory, "w") as z:
                z.writestr("colab_job.json", json.dumps(plan))
            archive_bytes = memory.getvalue()
        else:
            if not self.manual_job:
                from google.colab import files
                uploaded = files.upload()
                if len(uploaded) != 1:
                    raise ValueError("Choose one MVS job ZIP or one CSV/TSV file")
                self.manual_job = next(iter(uploaded))
            archive_bytes = Path(self.manual_job).read_bytes()
        if zipfile.is_zipfile(io.BytesIO(archive_bytes)):
            with zipfile.ZipFile(io.BytesIO(archive_bytes)) as z:
                # A desktop job always uses a flat root. Legacy one-root bundles are normalized.
                if "colab_job.json" in z.namelist():
                    plan = json.loads(z.read("colab_job.json"))
                else:
                    names = [n for n in z.namelist() if n.endswith("job.json") and not n.endswith("colab_job.json")]
                    if len(names) != 1:
                        raise ValueError("This ZIP is not an MVS job archive")
                    job = json.loads(z.read(names[0]))
                    plan = {"Key": hashlib.sha256(archive_bytes).hexdigest(), "Kind": "standard", "DatasetHash": ci(job, "DatasetHash"),
                            "SettingsHash": "", "Repetitions": ci(job, "Repetitions"), "Arguments": [], "RequestedAction": "calibrate"}
            key = ci(plan, "Key", "")
            if not re.fullmatch("[0-9a-f]{64}", key):
                raise ValueError("Invalid job identity")
            folder = self.root / key
            # Keep successful outputs; uploading a job again is not permission to overwrite them.
            incoming = self.root / ("incoming-" + uuid.uuid4().hex)
            safe_extract(io.BytesIO(archive_bytes), incoming)
            if not (incoming / "job.json").exists():
                nested = list(incoming.glob("*/job.json"))
                if len(nested) == 1:
                    incoming = nested[0].parent
            folder.mkdir(exist_ok=True)
            for item in incoming.rglob("*"):
                if item.is_file():
                    relative = item.relative_to(incoming)
                    destination = folder / relative
                    if relative.parts[0] in {"calibration", "analysis"} and destination.exists():
                        continue
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, destination)
            self.plan, self.folder = plan, folder
            if (folder / "job.json").exists():
                self.job = strict_json(folder / "job.json")
                self.input = folder / ci(self.job, "Dataset")
                if self.input.parent.resolve() != folder.resolve() or sha(self.input) != ci(plan, "DatasetHash"):
                    raise ValueError("Input hash differs from the job")
            else:
                self.job, self.input = {}, None
        else:
            if self.mode not in {"standard", "variance", "melsm"}:
                raise ValueError("Use a desktop job for a synthetic study")
            digest = hashlib.sha256(archive_bytes).hexdigest()
            key = hashlib.sha256((digest + self.mode + REVISION).encode()).hexdigest()
            self.folder = self.root / key
            self.folder.mkdir(exist_ok=True)
            self.input = self.folder / "data.csv"
            self.input.write_bytes(archive_bytes)
            self.job = {}
            self.plan = {"Key": key, "Kind": self.mode, "DatasetHash": digest, "SettingsHash": "", "Repetitions": 2000,
                         "Arguments": [], "RequestedAction": "calibrate"}
        self.phase = "preparing"
        self.send()
        try:
            self.install_cli()
            self.phase = "calibrated" if self.has_calibration() else "ready"
            if self.has_calibration():
                self.native_state_check()
            self.send(include_files=True)
        except KeyboardInterrupt:
            self.phase = "cancelled"; self.send(); raise
        except Exception:
            self.phase = "failed"; self.send(); raise
        self.show_monitor()
        return self

    @property
    def state_path(self):
        return self.folder / "calibration" / "calibration_state.json"

    def has_calibration(self):
        return bool(self.folder) and validate_calibration(self.state_path, self.plan)

    def packet(self, phase=None, include_files=False):
        packet = {"key": ci(self.plan, "Key"), "epoch": self.epoch, "phase": phase or self.phase, "notebookUrl": self.url}
        if include_files and self.has_calibration():
            packet["calibrationBase64"] = base64.b64encode(self.state_path.read_bytes()).decode()
        result_folder = find_run_folder(self.folder / "analysis")
        result = result_folder / "results.json" if result_folder else self.folder / "analysis" / "results.json"
        if include_files and result.exists():
            validate_manifest(result.parent, ci(self.plan, "DatasetHash"), ci(self.plan, "SettingsHash"))
            packet["resultsBase64"] = base64.b64encode(result.read_bytes()).decode()
            packet["manifestBase64"] = base64.b64encode((result.parent / "run_manifest.json").read_bytes()).decode()
        return packet

    def send(self, include_files=False):
        if not self.connection or not self.plan:
            return
        try:
            browser_request(self.connection, "status", self.packet(include_files=include_files))
            self.last_notice = ""
        except Exception as error:
            notice = "Desktop status is not connected. Keep MVS open and allow local access, or import the final results ZIP manually."
            if notice != self.last_notice:
                print(notice)
                self.last_notice = notice

    def run_process(self, command, allow_diagnostic=False):
        print("$", shlex.join(list(map(str, command))))
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                   encoding="utf-8", errors="replace", env=dotnet_environment(self.dotnet) if self.dotnet else None)
        output_queue = queue.Queue()
        def read_lines():
            for line in process.stdout:
                output_queue.put(line)
        reader = threading.Thread(target=read_lines, daemon=True)
        reader.start()
        last_ping = 0
        try:
            while process.poll() is None or reader.is_alive() or not output_queue.empty():
                try:
                    print(output_queue.get(timeout=.3), end="")
                except queue.Empty:
                    pass
                if time.monotonic() - last_ping > 15:
                    self.send()
                    last_ping = time.monotonic()
            code = process.wait()
            if code != 0 and not (allow_diagnostic and code == 2):
                raise RuntimeError(f"The step failed with exit code {code}; see the message above. No success status was recorded.")
            if code == 2:
                print("Diagnostic report saved; a model diagnostic/benchmark threshold was not satisfied. Inspect it before use.")
            return code
        except BaseException:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            raise

    def install_cli(self):
        self.dotnet = Path("/content/dotnet/dotnet")
        if not self.dotnet.exists():
            script = self.root / "dotnet-install.sh"
            with urllib.request.urlopen("https://dot.net/v1/dotnet-install.sh", timeout=60) as response:
                script.write_bytes(response.read())
            self.run_process(["bash", str(script), "--channel", "8.0", "--install-dir", str(self.dotnet.parent), "--no-path"])
        os.environ.update({k: v for k, v in dotnet_environment(self.dotnet).items() if k in {"PATH", "DOTNET_ROOT", "DOTNET_ROOT_X64", "DOTNET_CLI_TELEMETRY_OPTOUT"}})
        source_zip = self.folder / "cli-source.zip"
        source = self.root / "sources" / (sha(source_zip) if source_zip.exists() else hashlib.sha256(self.ref.encode()).hexdigest())
        if source_zip.exists():
            if not (source / "MvsAnalyzer.Cli/MvsAnalyzer.Cli.csproj").exists():
                safe_extract(source_zip, source)
        else:
            if not (source / ".git").exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                self.run_process(["git", "clone", "--depth", "1", "--branch", self.ref, "https://github.com/d1d2dopamine/MVS-Analyzer.git", str(source)])
            revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
            print("Source revision:", revision)
        binary = source / "colab-publish"
        self.dll = binary / "mvs.dll"
        if not self.dll.exists():
            self.run_process([str(self.dotnet), "publish", str(source / "MvsAnalyzer.Cli/MvsAnalyzer.Cli.csproj"), "-c", "Release", "-o", str(binary),
                              "--nologo", "-v", "minimal", "-p:UseAppHost=false"])
        info = subprocess.check_output(cli_command(self.dotnet, self.dll, "version"), env=dotnet_environment(self.dotnet), text=True)
        print(info)
        if APP_VERSION not in info or ENGINE_VERSION not in info or REVISION not in info:
            raise RuntimeError("This CLI does not match this notebook/job. Update the source, rather than reusing an older release.")

    def refresh(self):
        if self.connection:
            try:
                pending = browser_request(self.connection, "request")
                if ci(pending, "Key") != ci(self.plan, "Key"):
                    self.activate()
                else:
                    self.plan = pending
            except ConnectionError:
                print("Cannot refresh the desktop request; keeping the current, already loaded job.")

    @contextlib.contextmanager
    def phase_lock(self):
        import fcntl
        with open(self.folder / ".run.lock", "a+") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("This MVS job is already running; a second copy was not started.")
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def calibrate(self):
        self.refresh()
        if ci(self.plan, "Kind") != "standard":
            print("Prepared. Run the second cell for this additional method.")
            return
        with self.phase_lock():
            if self.has_calibration():
                self.native_state_check()
                print("✓ Calibration already exists for these exact data/settings. It was reused, not run again.")
                self.phase = "calibrated"
                self.send(include_files=True)
                return
            if self.state_path.exists():
                raise RuntimeError("An incompatible calibration exists. It was not overwritten; use a new matching job.")
            self.phase = "calibrating"
            self.send()
            args = ["calibrate", "--in", str(self.input), "--out", str(self.state_path.parent)]
            if self.job:
                args += ["--job", str(self.folder / "job.json")]
            else:
                args += ["--repetitions", str(ci(self.plan, "Repetitions")), "--seed", "20260719"]
            args += ci(self.plan, "Arguments", [])
            try:
                self.run_process(cli_command(self.dotnet, self.dll, *args))
                if not self.has_calibration():
                    raise RuntimeError("The saved calibration did not pass identity/format checks")
                self.native_state_check()
                self.phase = "calibrated"
                self.send(include_files=True)
            except KeyboardInterrupt:
                self.phase = "cancelled"; self.send(); raise
            except Exception:
                self.phase = "failed"; self.send(); raise
        self.show_monitor()

    def native_state_check(self):
        self.run_process(cli_command(self.dotnet, self.dll, "state-check", "--calibration", str(self.state_path), "--in", str(self.input)))

    def analyze(self):
        self.refresh()
        kind = ci(self.plan, "Kind")
        folder = self.folder / ("analysis" if kind == "standard" else kind)
        with self.phase_lock():
            completed = find_run_folder(folder)
            if completed:
                validate_manifest(completed, ci(self.plan, "DatasetHash") if self.input else None,
                                  ci(self.plan, "SettingsHash") if kind == "standard" else None)
                receipt = folder / "completion.json"
                code = ci(strict_json(receipt), "exitCode") if receipt.exists() else None
                print("✓ Saved outputs already exist; they were not overwritten.")
                self.phase = "complete" if code == 0 or kind == "standard" else "failed"
                if self.phase == "failed":
                    print("This is a diagnostic report, or its completion status is unconfirmed. It is not a successful validation.")
                self.send(include_files=True); return
            if kind == "standard" and not self.has_calibration():
                raise RuntimeError("Run the first cell to calibrate before starting the analysis")
            self.phase = "analyzing" if kind == "standard" else "running"
            self.send()
            if kind == "standard":
                if not self.has_calibration():
                    raise RuntimeError("Run the calibration cell first, or upload a matching completed calibration")
                args = ["analyze", "--in", str(self.input), "--calibration", str(self.state_path.parent), "--out", str(folder)] + ci(self.plan, "Arguments", [])
                if self.job:
                    args += ["--job", str(self.folder / "job.json")]
            else:
                args = [kind, "--out", str(folder)] + ci(self.plan, "Arguments", [])
                if self.input:
                    args += ["--in", str(self.input)]
                    profile = self.folder / "import_profile.json"
                    if profile.exists():
                        args += ["--import-profile", str(profile)]
            try:
                code = self.run_process(cli_command(self.dotnet, self.dll, *args), allow_diagnostic=kind != "standard")
                saved = find_run_folder(folder)
                if not saved:
                    raise RuntimeError("No completed manifest was produced; partial output is not success")
                validate_manifest(saved, ci(self.plan, "DatasetHash") if self.input else None,
                                  ci(self.plan, "SettingsHash") if kind == "standard" else None)
                (folder / "completion.json").write_text(json.dumps({"exitCode": code, "key": ci(self.plan, "Key")}))
                self.phase = "complete" if code == 0 else "failed"
                self.send(include_files=True)
            except KeyboardInterrupt:
                self.phase = "cancelled"; self.send(); raise
            except Exception:
                self.phase = "failed"; self.send(); raise
        self.show_monitor()

    def show_monitor(self):
        if not self.connection:
            return
        from google.colab import output
        from IPython.display import HTML, JSON, display
        def heartbeat():
            return JSON(self.packet())
        output.register_callback("mvs.colab_heartbeat", heartbeat)
        # The kernel callback must answer before the desktop is pinged. A tab being open
        # alone is deliberately NOT treated as a live Python runtime.
        script = """<div id="mvs-state" style="font:14px system-ui;padding:12px;border:1px solid #ddd;border-radius:8px">MVS · connected notebook status</div>
        <script>(function(){
          const destination = DESTINATION;
          let busy = false, failures = 0;
          async function ping(){
            if(busy || failures > 8) return; busy = true;
            try {
              const result = await google.colab.kernel.invokeFunction('mvs.colab_heartbeat', [], {});
              const packet = result.data['application/json'];
              const control = new AbortController(); const timeout = setTimeout(()=>control.abort(),5000);
              try {
                const reply=await fetch(destination,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(packet),credentials:'omit',cache:'no-store',signal:control.signal});
                if(!reply.ok) throw Error(reply.status);
                document.getElementById('mvs-state').textContent='MVS · '+packet.phase+' · desktop connected'; failures=0;
              } finally {clearTimeout(timeout);}
            } catch(error){failures++;document.getElementById('mvs-state').textContent='MVS · desktop not connected; manual result import remains available';}
            finally{busy=false;}
          }
          setInterval(ping,30000); ping();
        })();</script>""".replace("DESTINATION", json.dumps(self.connection + "/status"))
        display(HTML(script))
        if not self.url:
            try:
                import ipywidgets as widgets
                url_box = widgets.Text(placeholder="https://colab.research.google.com/drive/…", description="Notebook URL", layout=widgets.Layout(width="95%"))
                bind = widgets.Button(description="Link this notebook")
                notice = widgets.Label("If automatic URL detection failed, paste this notebook's address once. It does not need to be public.")
                def connect_url(_):
                    if not re.fullmatch(r"https://colab\.research\.google\.com/drive/[A-Za-z0-9_-]{10,}(?:[?#].*)?", url_box.value.strip()):
                        notice.value = "Use the saved notebook's /drive/ address, not a GitHub or public-share link."
                        return
                    self.url = url_box.value.strip().split("#")[0].split("?")[0]
                    self.send(include_files=True)
                    notice.value = "Notebook linked. The desktop can reopen this same notebook."
                    bind.disabled = True
                bind.on_click(connect_url)
                display(widgets.VBox([notice, url_box, bind]))
            except ImportError:
                print("Notebook URL unavailable; automatic notebook reuse is not confirmed. Keep this browser tab or use manual result import.")

    def download(self):
        allowed = ["calibration", "analysis", "variance", "melsm", "estimation", "benchmark"]
        archive = self.root / ("MVS_results_" + ci(self.plan, "Key")[:12] + ".zip")
        count = 0
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for name in allowed:
                original = self.folder / name
                directory = original if name == "calibration" else find_run_folder(original) or original
                for path in directory.rglob("*"):
                    if path.is_file() and path.suffix != ".tmp":
                        z.write(path, name + "/" + path.relative_to(directory).as_posix()); count += 1
                receipt = original / "completion.json"
                if receipt.exists() and directory != original:
                    z.write(receipt, name + "/completion.json")
            z.writestr("README.txt", "MVS outputs. Calibration belongs to exact data/settings. Numerical diagnostics are not independent validation. Input data, connection tokens and source files are not included.\n")
        if count == 0:
            archive.unlink(missing_ok=True)
            raise RuntimeError("No outputs exist yet. Run the preceding cells first.")
        self.send(include_files=True)
        from google.colab import files
        files.download(str(archive))
        return archive
