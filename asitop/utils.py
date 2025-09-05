import os
import glob
import subprocess
from subprocess import PIPE
import psutil
from .parsers import *
import plistlib


def parse_powermetrics(path='/tmp/asitop_powermetrics', timecode="0"):
    data = None
    try:
        with open(path+timecode, 'rb') as fp:
            data = fp.read()
        data = data.split(b'\x00')
        powermetrics_parse = plistlib.loads(data[-1])
        thermal_pressure = parse_thermal_pressure(powermetrics_parse)
        cpu_metrics_dict = parse_cpu_metrics(powermetrics_parse)
        gpu_metrics_dict = parse_gpu_metrics(powermetrics_parse)
        #bandwidth_metrics = parse_bandwidth_metrics(powermetrics_parse)
        bandwidth_metrics = None
        timestamp = powermetrics_parse["timestamp"]
        return cpu_metrics_dict, gpu_metrics_dict, thermal_pressure, bandwidth_metrics, timestamp
    except Exception as e:
        if data:
            if len(data) > 1:
                powermetrics_parse = plistlib.loads(data[-2])
                thermal_pressure = parse_thermal_pressure(powermetrics_parse)
                cpu_metrics_dict = parse_cpu_metrics(powermetrics_parse)
                gpu_metrics_dict = parse_gpu_metrics(powermetrics_parse)
                #bandwidth_metrics = parse_bandwidth_metrics(powermetrics_parse)
                bandwidth_metrics = None
                timestamp = powermetrics_parse["timestamp"]
                return cpu_metrics_dict, gpu_metrics_dict, thermal_pressure, bandwidth_metrics, timestamp
        return False


def clear_console():
    command = 'clear'
    os.system(command)


def convert_to_GB(value):
    return round(value/1024/1024/1024, 1)


def run_powermetrics_process(timecode, nice=10, interval=1000):
    #ver, *_ = platform.mac_ver()
    #major_ver = int(ver.split(".")[0])
    for tmpf in glob.glob("/tmp/asitop_powermetrics*"):
        os.remove(tmpf)
    output_file_flag = "-o"
    command = " ".join([
        "sudo nice -n",
        str(nice),
        "powermetrics",
        "--samplers cpu_power,gpu_power,thermal",
        output_file_flag,
        "/tmp/asitop_powermetrics"+timecode,
        "-f plist",
        "-i",
        str(interval)
    ])
    process = subprocess.Popen(command.split(" "), stdin=PIPE, stdout=PIPE)
    return process


def get_ram_metrics_dict():
    ram_metrics = psutil.virtual_memory()
    swap_metrics = psutil.swap_memory()
    total_GB = convert_to_GB(ram_metrics.total)
    free_GB = convert_to_GB(ram_metrics.available)
    used_GB = convert_to_GB(ram_metrics.total-ram_metrics.available)
    swap_total_GB = convert_to_GB(swap_metrics.total)
    swap_used_GB = convert_to_GB(swap_metrics.used)
    swap_free_GB = convert_to_GB(swap_metrics.total-swap_metrics.used)
    if swap_total_GB > 0:
        swap_free_percent = int(100-(swap_free_GB/swap_total_GB*100))
    else:
        swap_free_percent = None
    ram_metrics_dict = {
        "total_GB": round(total_GB, 1),
        "free_GB": round(free_GB, 1),
        "used_GB": round(used_GB, 1),
        "free_percent": int(100-(ram_metrics.available/ram_metrics.total*100)),
        "swap_total_GB": swap_total_GB,
        "swap_used_GB": swap_used_GB,
        "swap_free_GB": swap_free_GB,
        "swap_free_percent": swap_free_percent,
    }
    return ram_metrics_dict


def get_cpu_info():
    cpu_info = os.popen('sysctl -a | grep machdep.cpu').read()
    cpu_info_lines = cpu_info.split("\n")
    data_fields = ["machdep.cpu.brand_string", "machdep.cpu.core_count"]
    cpu_info_dict = {}
    for l in cpu_info_lines:
        for h in data_fields:
            if h in l:
                value = l.split(":")[1].strip()
                cpu_info_dict[h] = value
    return cpu_info_dict


def get_core_counts():
    cores_info = os.popen('sysctl -a | grep hw.perflevel').read()
    cores_info_lines = cores_info.split("\n")
    data_fields = ["hw.perflevel0.logicalcpu", "hw.perflevel1.logicalcpu"]
    cores_info_dict = {}
    for l in cores_info_lines:
        for h in data_fields:
            if h in l:
                value = int(l.split(":")[1].strip())
                cores_info_dict[h] = value
    return cores_info_dict


def get_gpu_cores():
    try:
        cores = os.popen(
            "system_profiler -detailLevel basic SPDisplaysDataType | grep 'Total Number of Cores'").read()
        cores = int(cores.split(": ")[-1])
    except:
        cores = "?"
    return cores


def get_soc_info():
    """Returns a dict of SOC info"""
    soc_info_dict = {}

    # Get CPU info from sysctl
    cpu_info_dict = get_cpu_info()

    # Get SOC name
    soc_name = cpu_info_dict.get("machdep.cpu.brand_string")
    if soc_name is None:
        # Fallback for Linux systems or when the key is not available
        soc_name = cpu_info_dict.get("model name", "Unknown")

    soc_info_dict["name"] = soc_name
    cpu_info_dict = get_cpu_info()
    core_counts_dict = get_core_counts()
    try:
        e_core_count = core_counts_dict["hw.perflevel1.logicalcpu"]
        p_core_count = core_counts_dict["hw.perflevel0.logicalcpu"]
    except:
        e_core_count = "?"
        p_core_count = "?"
    soc_info = {
        "name": cpu_info_dict["machdep.cpu.brand_string"],
        "core_count": int(cpu_info_dict["machdep.cpu.core_count"]),
        "cpu_max_power": None,
        "gpu_max_power": None,
        "cpu_max_bw": None,
        "gpu_max_bw": None,
        "e_core_count": e_core_count,
        "p_core_count": p_core_count,
        "gpu_core_count": get_gpu_cores()
    }
# A lookup table for TDP and bandwidth based on SOC name
SOC_SPECS = {
    # M1 Series
    "Apple M1": {"cpu_max_power": 20, "gpu_max_power": 20, "cpu_max_bw": 70, "gpu_max_bw": 70},
    "Apple M1 Pro": {"cpu_max_power": 30, "gpu_max_power": 30, "cpu_max_bw": 200, "gpu_max_bw": 200},
    "Apple M1 Max": {"cpu_max_power": 30, "gpu_max_power": 60, "cpu_max_bw": 250, "gpu_max_bw": 400},
    "Apple M1 Ultra": {"cpu_max_power": 60, "gpu_max_power": 120, "cpu_max_bw": 500, "gpu_max_bw": 800},
    
    # M2 Series
    "Apple M2": {"cpu_max_power": 25, "gpu_max_power": 15, "cpu_max_bw": 100, "gpu_max_bw": 100},
    "Apple M2 Pro": {"cpu_max_power": 30, "gpu_max_power": 30, "cpu_max_bw": 200, "gpu_max_bw": 200},
    "Apple M2 Max": {"cpu_max_power": 30, "gpu_max_power": 60, "cpu_max_bw": 250, "gpu_max_bw": 400},
    "Apple M2 Ultra": {"cpu_max_power": 60, "gpu_max_power": 120, "cpu_max_bw": 400, "gpu_max_bw": 800},
    
    # M3 Series
    "Apple M3": {"cpu_max_power": 25, "gpu_max_power": 15, "cpu_max_bw": 100, "gpu_max_bw": 100},
    "Apple M3 Pro": {"cpu_max_power": 30, "gpu_max_power": 30, "cpu_max_bw": 150, "gpu_max_bw": 150},
    "Apple M3 Max": {"cpu_max_power": 30, "gpu_max_power": 60, "cpu_max_bw": 300, "gpu_max_bw": 400},
    
    # M4 Series
    "Apple M4": {"cpu_max_power": 25, "gpu_max_power": 15, "cpu_max_bw": 120, "gpu_max_bw": 120},
    "Apple M4 Pro": {"cpu_max_power": 30, "gpu_max_power": 30, "cpu_max_bw": 273, "gpu_max_bw": 273},
    "Apple M4 Max": {"cpu_max_power": 30, "gpu_max_power": 60, "cpu_max_bw": 410, "gpu_max_bw": 546}
}

# The initial `soc_info` dictionary
soc_info = {
    "name": cpu_info_dict["machdep.cpu.brand_string"],
    "core_count": int(cpu_info_dict["machdep.cpu.core_count"]),
    "cpu_max_power": None,
    "gpu_max_power": None,
    "cpu_max_bw": None,
    "gpu_max_bw": None,
    "e_core_count": e_core_count,
    "p_core_count": p_core_count,
    "gpu_core_count": get_gpu_cores()
}
# A simple way to get max values for the M4 Max based on its core count
if "M4 Max" in soc_info["name"]:
    if soc_info["core_count"] == 14:
        soc_info["cpu_max_bw"] = 410
        soc_info["gpu_max_bw"] = 410
    elif soc_info["core_count"] == 16:
        soc_info["cpu_max_bw"] = 546
        soc_info["gpu_max_bw"] = 546
    
    # Update other values for M4 Max
    soc_info["cpu_max_power"] = 30
    soc_info["gpu_max_power"] = 60

# For all other models, use the lookup table
else:
    soc_info.update(SOC_SPECS.get(soc_info["name"], {"cpu_max_power": 20, "gpu_max_power": 20, "cpu_max_bw": 70, "gpu_max_bw": 70}))

return soc_info
