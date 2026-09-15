"""AdbClient: typed wrapper over adb. Commands drawn from Appendix A.

Every method delegates to ProcessRunner (one-shot) or returns an AdbStream
(long-lived). No parsing logic belongs above this layer — callers get typed
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

    def list_devices(self) -> list[Device]:
        result = self._runner.run(self._adb_path, ["devices", "-l"])
        devices: list[Device] = []
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
            tokens = {k: v for k, v in (t.split(":", 1) for t in parts[2:] if ":" in t)}
            device = Device(serial=serial, state=state, model=tokens.get("model"))
            if state == "device":
                device.model = self.getprop(serial, "ro.product.model") or tokens.get("model")
                device.android_version = self.getprop(serial, "ro.build.version.release") or None
                sdk = self.getprop(serial, "ro.build.version.sdk")
                device.api_level = int(sdk) if sdk.isdigit() else None
                device.abi = self.getprop(serial, "ro.product.cpu.abi") or None
                density = self.getprop(serial, "ro.sf.lcd_density")
                device.density = int(density) if density.isdigit() else None
            devices.append(device)
        return devices

    def getprop(self, serial: str, prop: str) -> str:
        result = self._runner.run(self._adb_path, ["-s", serial, "shell", "getprop", prop])
        return result.stdout.strip()

    def pair(self, host_port: str, pairing_code: str) -> bool:
        result = self._runner.run(self._adb_path, ["pair", host_port, pairing_code])
        return result.exit_code == 0

    def connect(self, host_port: str) -> bool:
        result = self._runner.run(self._adb_path, ["connect", host_port])
        return result.exit_code == 0

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
        return self._runner.run_bytes(
            self._adb_path, ["-s", serial, "exec-out", "screencap", "-p"]
        )

    def logcat_dump(self, serial: str, pid: int | None = None) -> list[str]:
        args = ["-s", serial, "logcat", "-d", "-v", "threadtime"]
        if pid is not None:
            args.append(f"--pid={pid}")
        result = self._runner.run(self._adb_path, args)
        return [line for line in result.stdout.splitlines() if line.strip()]
