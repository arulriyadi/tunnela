import importlib.metadata
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import threading

import psutil
from flask import current_app

_cpu_static_info_cache: dict | None = None
_runtime_versions_cache: dict | None = None
_runtime_versions_cache_time: float = 0.0
_RUNTIME_VERSIONS_TTL = 60.0


def _cpu_static_info() -> dict:
    """Logical/physical core counts and CPU model (cached for process lifetime)."""
    global _cpu_static_info_cache
    if _cpu_static_info_cache is not None:
        return _cpu_static_info_cache
    logical = psutil.cpu_count(logical=True) or 0
    physical = psutil.cpu_count(logical=False)
    model = ""
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/cpuinfo", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    low = line.lower()
                    if low.startswith("model name") or low.startswith("cpu model") or low.startswith(
                        "processor model"
                    ):
                        model = line.split(":", 1)[1].strip()
                        break
                    if low.startswith("hardware\t") or low.startswith("hardware "):
                        model = line.split(":", 1)[1].strip()
        if not model:
            model = (platform.processor() or "").strip()
    except OSError:
        model = (platform.processor() or "").strip()
    _cpu_static_info_cache = {
        "logical_cores": int(logical),
        "physical_cores": int(physical) if physical is not None else None,
        "model": model[:200] if model else "",
    }
    return _cpu_static_info_cache


def _resolve_nginx_binary() -> str | None:
    p = shutil.which("nginx")
    if p:
        return p
    for path in (
        "/usr/sbin/nginx",
        "/usr/local/sbin/nginx",
        "/usr/local/nginx/sbin/nginx",
        "/opt/nginx/sbin/nginx",
    ):
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def _runtime_versions_snapshot() -> dict:
    """Versions of stack tools; safe for frequent polling (caller may cache)."""
    out: dict = {
        "python": None,
        "gunicorn": None,
        "nginx": None,
        "wireguard_tools": None,
        "openssl": None,
        "flask": None,
    }
    try:
        v = sys.version_info
        out["python"] = f"{v.major}.{v.minor}.{v.micro}"
    except Exception:
        pass
    try:
        out["gunicorn"] = importlib.metadata.version("gunicorn")
    except Exception:
        gunicorn_exe = shutil.which("gunicorn")
        if not gunicorn_exe:
            cand = os.path.join(os.getcwd(), "venv", "bin", "gunicorn")
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                gunicorn_exe = cand
        if gunicorn_exe:
            try:
                p = subprocess.run(
                    [gunicorn_exe, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=4,
                )
                line = (p.stdout or p.stderr or "").strip().split("\n")[0]
                if line:
                    out["gunicorn"] = line
            except Exception:
                pass
    try:
        out["flask"] = importlib.metadata.version("flask")
    except Exception:
        pass

    bin_nginx = _resolve_nginx_binary()
    if bin_nginx:
        try:
            p = subprocess.run([bin_nginx, "-v"], capture_output=True, text=True, timeout=4)
            line = ((p.stderr or "").strip() or (p.stdout or "").strip()).split("\n")[0]
            out["nginx"] = line or None
        except Exception:
            out["nginx"] = None

    wg = shutil.which("wg")
    if wg:
        try:
            p = subprocess.run([wg, "--version"], capture_output=True, text=True, timeout=4)
            line = ((p.stdout or "").strip() or (p.stderr or "").strip()).split("\n")[0]
            out["wireguard_tools"] = line or None
        except Exception:
            out["wireguard_tools"] = None

    openssl_bin = shutil.which("openssl")
    if openssl_bin:
        try:
            p = subprocess.run([openssl_bin, "version"], capture_output=True, text=True, timeout=4)
            line = (p.stdout or "").strip().split("\n")[0]
            out["openssl"] = line or None
        except Exception:
            out["openssl"] = None
    return out


def _runtime_versions_snapshot_cached() -> dict:
    global _runtime_versions_cache, _runtime_versions_cache_time
    now = time.time()
    if (
        _runtime_versions_cache is not None
        and now - _runtime_versions_cache_time < _RUNTIME_VERSIONS_TTL
    ):
        return _runtime_versions_cache
    _runtime_versions_cache = _runtime_versions_snapshot()
    _runtime_versions_cache_time = now
    return _runtime_versions_cache


def _host_snapshot():
    """Primary IPv4 via default-route probe; uptime from boot time."""
    try:
        boot = psutil.boot_time()
        uptime_seconds = int(max(0, time.time() - boot))
    except Exception:
        uptime_seconds = 0
    primary_ipv4 = ""
    for dest in (("8.8.8.8", 53), ("1.1.1.1", 80)):
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(0.25)
            sock.connect(dest)
            primary_ipv4 = sock.getsockname()[0]
            break
        except OSError:
            pass
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
    return {"uptime_seconds": uptime_seconds, "primary_ipv4": primary_ipv4}


class SystemStatus:
    def __init__(self):
        self.CPU = CPU()
        self.MemoryVirtual = Memory('virtual')
        self.MemorySwap = Memory('swap')
        self.Disks = Disks()
        self.NetworkInterfaces = NetworkInterfaces()
        self.Processes = Processes()
    def toJson(self):
        process = [
            threading.Thread(target=self.CPU.getCPUPercent), 
            threading.Thread(target=self.CPU.getPerCPUPercent),
            threading.Thread(target=self.NetworkInterfaces.getData)
        ]
        for p in process:
            p.start()
        for p in process:
            p.join()
        
        
        return {
            "CPU": self.CPU,
            "Memory": {
                "VirtualMemory": self.MemoryVirtual,
                "SwapMemory": self.MemorySwap
            },
            "Disks": self.Disks,
            "NetworkInterfaces": self.NetworkInterfaces,
            "NetworkInterfacesPriority": self.NetworkInterfaces.getInterfacePriorities(),
            "Processes": self.Processes,
            "Host": _host_snapshot(),
            "RuntimeVersions": _runtime_versions_snapshot_cached(),
        }
        

class CPU:
    def __init__(self):
        self.cpu_percent: float = 0
        self.cpu_percent_per_cpu: list[float] = []
        self.logical_cores: int = 0
        self.physical_cores: int | None = None
        self.model: str = ""

    def getCPUPercent(self):
        try:
            self.cpu_percent = psutil.cpu_percent(interval=1)
        except Exception as e:
            current_app.logger.error("Get CPU Percent error", e)
    
    def getPerCPUPercent(self):
        try:
            self.cpu_percent_per_cpu = psutil.cpu_percent(interval=1, percpu=True)
        except Exception as e:
            current_app.logger.error("Get Per CPU Percent error", e)

    def toJson(self):
        static = _cpu_static_info()
        self.logical_cores = static["logical_cores"]
        self.physical_cores = static["physical_cores"]
        self.model = static["model"]
        return self.__dict__


class Memory:
    def __init__(self, memoryType: str):
        self.__memoryType__ = memoryType
        self.total = 0
        self.used = 0
        self.available = 0
        self.percent = 0

    def getData(self):
        try:
            if self.__memoryType__ == "virtual":
                memory = psutil.virtual_memory()
                self.available = memory.available
                self.used = memory.used
            else:
                memory = psutil.swap_memory()
                self.available = memory.free
                self.used = memory.used
            self.total = memory.total
            self.percent = memory.percent
        except Exception as e:
            current_app.logger.error("Get Memory percent error", e)
    def toJson(self):
        self.getData()
        return self.__dict__

class Disks:
    def __init__(self):
        self.disks : list[Disk] = []
    def getData(self):
        try:
            self.disks = list(map(lambda x : Disk(x.mountpoint), psutil.disk_partitions()))
        except Exception as e:
            current_app.logger.error("Get Disk percent error", e)
    def toJson(self):
        self.getData()
        return self.disks

class Disk:
    def __init__(self, mountPoint: str):
        self.total = 0
        self.used = 0
        self.free = 0
        self.percent = 0
        self.mountPoint = mountPoint
    def getData(self):
        try:
            disk = psutil.disk_usage(self.mountPoint)
            self.total = disk.total
            self.free = disk.free
            self.used = disk.used
            self.percent = disk.percent
        except Exception as e:
            current_app.logger.error("Get Disk percent error", e)
    def toJson(self):
        self.getData()
        return self.__dict__
    
class NetworkInterfaces:
    def __init__(self):
        self.interfaces = {}
        
    def getInterfacePriorities(self):
        if shutil.which("ip"):
            result = subprocess.check_output(["ip", "route", "show"]).decode()
            priorities = {}
            for line in result.splitlines():
                if "metric" in line and "dev" in line:
                    parts = line.split()
                    dev = parts[parts.index("dev")+1]
                    metric = int(parts[parts.index("metric")+1])
                    if dev not in priorities:
                        priorities[dev] = metric
            return priorities
        return {}

    def getData(self):
        self.interfaces.clear()
        try:
            network = psutil.net_io_counters(pernic=True, nowrap=True)
            for i in network.keys():
                self.interfaces[i] = network[i]._asdict()
            time.sleep(1)
            network = psutil.net_io_counters(pernic=True, nowrap=True)
            for i in network.keys():
                self.interfaces[i]['realtime'] = {
                    'sent': round((network[i].bytes_sent - self.interfaces[i]['bytes_sent']) / 1024 / 1024, 4),
                    'recv': round((network[i].bytes_recv - self.interfaces[i]['bytes_recv']) / 1024 / 1024, 4)
                }
        except Exception as e:
            current_app.logger.error("Get network error", e)

    def toJson(self):
        return self.interfaces

class Process:
    def __init__(self, name, command, pid, percent):
        self.name = name
        self.command = command
        self.pid = pid
        self.percent = percent
    def toJson(self):
        return self.__dict__

class Processes:
    def __init__(self):
        self.CPU_Top_10_Processes: list[Process] = []
        self.Memory_Top_10_Processes: list[Process] = []
    def getData(self):
        try:
            processes = list(psutil.process_iter())

            cpu_processes = []
            memory_processes = []

            for proc in processes:
                try:
                    name = proc.name()
                    cmdline = " ".join(proc.cmdline())
                    pid = proc.pid
                    cpu_percent = proc.cpu_percent()
                    mem_percent = proc.memory_percent()

                    # Create Process object for CPU and memory tracking
                    cpu_process = Process(name, cmdline, pid, cpu_percent)
                    mem_process = Process(name, cmdline, pid, mem_percent)

                    cpu_processes.append(cpu_process)
                    memory_processes.append(mem_process)

                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    # Skip processes we can’t access or that no longer exist
                    continue

            # Sort by CPU and memory usage (descending order)
            cpu_sorted = sorted(cpu_processes, key=lambda p: p.percent, reverse=True)
            mem_sorted = sorted(memory_processes, key=lambda p: p.percent, reverse=True)

            # Get top 20 processes for each
            self.CPU_Top_10_Processes = cpu_sorted[:20]
            self.Memory_Top_10_Processes = mem_sorted[:20]

        except Exception as e:
            current_app.logger.error("Get processes error", e)

    def toJson(self):
        self.getData()
        return {
            "cpu_top_10": self.CPU_Top_10_Processes,
            "memory_top_10": self.Memory_Top_10_Processes
        }