"""AdbClient: typed wrapper over adb. Commands drawn from Appendix A.

Every method delegates to ProcessRunner (one-shot) or returns an AdbStream
(long-lived). No parsing logic belongs above this layer - callers get typed
results, not raw adb text.
"""

from __future__ import annotations

from pathlib import Path

from droiddesk.core.models import Device
from droiddesk.infra.process import AdbStream, ProcessRunner


class AdbClient:
    def __init__(self, adb_path: Path, runner: ProcessRunner | None = None) -> None:
        self._adb_path = adb_path
        self._runner = runner or ProcessRunner()
        self._device_props_cache: dict[str, dict[str, str]] = {}

    @property
    def adb_path(self) -> Path:
        return self._adb_path

    def set_adb_path(self, path: Path) -> None:
        self._adb_path = path

    def get_all_props(self, serial: str) -> dict[str, str]:
        """Fetch and cache all getprop properties for a device in a single fast call."""
        if serial in self._device_props_cache:
            return self._device_props_cache[serial]

        result = self._runner.run(
            self._adb_path, ["-s", serial, "shell", "getprop"], timeout=10.0
        )
        props: dict[str, str] = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("[") and "]: [" in line:
                key, val = line[1:].split("]: [", 1)
                props[key] = val.rstrip("]")

        if props:
            self._device_props_cache[serial] = props
        return props

    def list_devices(self) -> list[Device]:
        result = self._runner.run(self._adb_path, ["devices", "-l"], timeout=10.0)
        devices: list[Device] = []
        active_serials: set[str] = set()

        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("List of devices"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            serial, state = parts[0], parts[1]
            if state not in ("device", "unauthorized", "offline"):
                continue

            active_serials.add(serial)
            tokens = {k: v for k, v in (t.split(":", 1) for t in parts[2:] if ":" in t)}
            device = Device(serial=serial, state=state, model=tokens.get("model"))
            if state == "device":
                props = self.get_all_props(serial)
                device.model = props.get("ro.product.model") or tokens.get("model")
                device.android_version = props.get("ro.build.version.release") or None
                sdk = props.get("ro.build.version.sdk")
                device.api_level = int(sdk) if sdk and sdk.isdigit() else None
                device.abi = props.get("ro.product.cpu.abi") or None
                density = props.get("ro.sf.lcd_density")
                device.density = int(density) if density and density.isdigit() else None
            devices.append(device)

        # Evict disconnected serials from the property cache
        for cached_serial in list(self._device_props_cache.keys()):
            if cached_serial not in active_serials:
                self._device_props_cache.pop(cached_serial, None)

        return devices

    def getprop(self, serial: str, prop: str) -> str:
        if serial in self._device_props_cache:
            return self._device_props_cache[serial].get(prop, "")
        result = self._runner.run(self._adb_path, ["-s", serial, "shell", "getprop", prop])
        return result.stdout.strip()


    def pair(self, host_port: str, pairing_code: str) -> bool:
        result = self._runner.run(self._adb_path, ["pair", host_port, pairing_code])
        return result.exit_code == 0

    def connect(self, host_port: str) -> tuple[bool, str]:
        result = self._runner.run(self._adb_path, ["connect", host_port], timeout=15.0)
        output = (result.stdout + " " + result.stderr).strip()
        low = output.lower()
        success = (
            result.exit_code == 0
            and ("connected to" in low or "already connected to" in low)
            and "failed" not in low
            and "cannot" not in low
            and "unable" not in low
        )
        return success, output

    def reconnect(self, serial: str) -> bool:
        result = self._runner.run(self._adb_path, ["-s", serial, "reconnect"])
        return result.exit_code == 0

    def install(
        self, serial: str, apk_path: Path, replace: bool = True, test_ok: bool = True
    ) -> bool:
        args = ["-s", serial, "install"]
        if replace:
            args.append("-r")
        if test_ok:
            args.append("-t")
        args.append(str(apk_path))
        result = self._runner.run(self._adb_path, args, timeout=120.0)
        return "Success" in result.stdout

    def uninstall(self, serial: str, package: str) -> bool:
        result = self._runner.run(self._adb_path, ["-s", serial, "uninstall", package])
        return "Success" in result.stdout

    def launch(self, serial: str, package: str) -> bool:
        result = self._runner.run(
            self._adb_path,
            [
                "-s",
                serial,
                "shell",
                "monkey",
                "-p",
                package,
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            ],
        )
        return result.exit_code == 0

    def pidof(self, serial: str, package: str) -> int | None:
        result = self._runner.run(self._adb_path, ["-s", serial, "shell", "pidof", package])
        pid = result.stdout.strip()
        return int(pid) if pid.isdigit() else None

    def force_stop(self, serial: str, package: str) -> None:
        self._runner.run(self._adb_path, ["-s", serial, "shell", "am", "force-stop", package])

    def dumpsys_package(self, serial: str, package: str) -> str:
        result = self._runner.run(
            self._adb_path, ["-s", serial, "shell", "dumpsys", "package", package]
        )
        return result.stdout

    def logcat_clear(self, serial: str) -> None:
        self._runner.run(self._adb_path, ["-s", serial, "logcat", "-c"])

    def logcat_stream(self, serial: str, pid: int | None = None) -> AdbStream:
        args = ["-s", serial, "logcat", "-v", "threadtime"]
        if pid is not None:
            args.insert(3, f"--pid={pid}")
        return AdbStream(self._adb_path, args)

    def screenshot(self, serial: str) -> bytes:
        raw = self._runner.run_bytes(
            self._adb_path, ["-s", serial, "exec-out", "screencap", "-p"], timeout=20.0
        )
        if raw.startswith(b"\x89PNG\r\n\x1a\n"):
            return raw
        if b"\x89PNG" in raw:
            fixed = raw.replace(b"\r\r\n", b"\r\n")
            if fixed.startswith(b"\x89PNG\r\n\x1a\n"):
                return fixed

        # Fallback to device-side capture and pull if exec-out is corrupted or unsupported
        safe_name = serial.replace(":", "_").replace("/", "_")
        tmp_remote = f"/sdcard/droiddesk_cap_{safe_name}.png"
        self._runner.run(
            self._adb_path, ["-s", serial, "shell", "screencap", "-p", tmp_remote], timeout=20.0
        )
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_local = Path(tmp.name)
        try:
            self._runner.run(
                self._adb_path, ["-s", serial, "pull", tmp_remote, str(tmp_local)], timeout=20.0
            )
            self._runner.run(
                self._adb_path, ["-s", serial, "shell", "rm", "-f", tmp_remote], timeout=5.0
            )
            if tmp_local.exists() and tmp_local.stat().st_size > 0:
                return tmp_local.read_bytes()
        finally:
            if tmp_local.exists():
                tmp_local.unlink(missing_ok=True)
        return raw

    def logcat_dump(self, serial: str, pid: int | None = None) -> list[str]:
        args = ["-s", serial, "logcat", "-d", "-v", "threadtime"]
        if pid is not None:
            args.append(f"--pid={pid}")
        result = self._runner.run(self._adb_path, args)
        return [line for line in result.stdout.splitlines() if line.strip()]
