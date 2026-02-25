import os
import shutil
import subprocess
from pathlib import Path


class LinuxProcAdapter:
    name = 'linux-proc'

    def __init__(self):
        self._prev_cpu = None

    def _read_meminfo(self):
        data = {}
        with open('/proc/meminfo', 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                parts = line.split(':', 1)
                if len(parts) != 2:
                    continue
                key = parts[0].strip()
                val = parts[1].strip().split()[0]
                data[key] = int(val)
        return data

    def _read_temp_c(self):
        try:
            raw = Path('/sys/class/thermal/thermal_zone0/temp').read_text().strip()
            return float(raw) / 1000.0
        except Exception:
            pass

        vcg = shutil.which('vcgencmd')
        if vcg:
            try:
                out = subprocess.check_output([vcg, 'measure_temp'], text=True, timeout=2)
                if 'temp=' in out:
                    v = out.split('temp=', 1)[1].split("'", 1)[0]
                    return float(v)
            except Exception:
                pass
        return None

    def sample(self):
        cpu_percent = None
        with open('/proc/stat', 'r', encoding='utf-8', errors='replace') as f:
            parts = f.readline().split()
            vals = [int(x) for x in parts[1:]]
            idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
            total = sum(vals)
            if self._prev_cpu:
                didle = idle - self._prev_cpu[0]
                dtotal = total - self._prev_cpu[1]
                if dtotal > 0:
                    cpu_percent = 100.0 * (1.0 - (didle / dtotal))
            self._prev_cpu = (idle, total)

        mem = self._read_meminfo()
        mem_total = mem.get('MemTotal', 0)
        mem_avail = mem.get('MemAvailable', 0)
        mem_percent = None
        if mem_total > 0:
            mem_percent = 100.0 * (1.0 - (mem_avail / mem_total))

        disk = shutil.disk_usage('/')
        disk_percent = 100.0 * (disk.used / disk.total) if disk.total else None

        load1, load5, load15 = os.getloadavg()
        cores = os.cpu_count() or 1
        load_1m_per_core = load1 / cores if cores else load1

        temp_c = self._read_temp_c()

        return {
            'host': {
                'hostname': os.uname().nodename,
                'cores': cores,
                'adapter': self.name,
            },
            'metrics': {
                'cpu_percent': round(cpu_percent, 3) if cpu_percent is not None else None,
                'mem_percent': round(mem_percent, 3) if mem_percent is not None else None,
                'disk_percent': round(disk_percent, 3) if disk_percent is not None else None,
                'temp_c': round(temp_c, 3) if temp_c is not None else None,
                'load_1m': round(load1, 3),
                'load_5m': round(load5, 3),
                'load_15m': round(load15, 3),
                'load_1m_per_core': round(load_1m_per_core, 3),
            },
        }
