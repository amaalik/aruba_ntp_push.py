#!/usr/bin/env python3
"""
Push NTP server config to Aruba switches in a fixed IP range over SSH.
Unreachable switches or failed logins are skipped and logged.

Usage:
    pip install netmiko
    python aruba_ntp_push.py

Results are written to ntp_push_results.csv.
"""
import csv
import ipaddress
from concurrent.futures import ThreadPoolExecutor
from netmiko import ConnectHandler

# ---- Settings you may need to change -------------------------------------
USERNAME = "admin"
PASSWORD = "password"  # edit before use

START_IP = "10.100.99.21"
END_IP = "10.100.99.96"

RESULT_FILE = "ntp_push_results.csv"

# Netmiko driver. Check which Aruba drivers your Netmiko version supports:
#   python -c "from netmiko.ssh_dispatcher import CLASS_MAPPER_BASE as m; print([k for k in m if 'aruba' in k or 'procurve' in k])"
# ArubaOS-Switch (2530/2930F/3810/5400R) -> "hp_procurve"
# AOS-CX -> use the Aruba CX driver if your version lists one.
DEVICE_TYPE = "hp_procurve"

# Commands pushed in config mode. Adjust for your OS:
#   AOS-CX:           ntp server <ip> / ntp enable
#   ArubaOS-Switch:   ntp server <ip> / ntp enable (newer builds), or
#                     sntp server priority 1 <ip> on older builds
CONFIG_COMMANDS = [
    "ntp server 10.100.20.130",
    "ntp server 10.100.20.131",
    "no ntp server 10.100.0.2",
    "no ntp server pool.ntp.org",
    "ntp enable",
]

SAVE_COMMAND = "write memory"
VERIFY_COMMAND = "show ntp associations"
MAX_WORKERS = 10
# ---------------------------------------------------------------------------


def ip_range(start, end):
    first = int(ipaddress.IPv4Address(start))
    last = int(ipaddress.IPv4Address(end))
    return [str(ipaddress.IPv4Address(i)) for i in range(first, last + 1)]


def configure_switch(ip):
    device = {
        "device_type": DEVICE_TYPE,
        "host": ip,
        "username": USERNAME,
        "password": PASSWORD,
        "fast_cli": False,
        "conn_timeout": 10,
        "auth_timeout": 15,
        "banner_timeout": 15,
    }
    try:
        with ConnectHandler(**device) as conn:
            conn.send_config_set(CONFIG_COMMANDS)
            conn.send_command(SAVE_COMMAND)
            verify = conn.send_command(VERIFY_COMMAND)
        print(f"[OK]      {ip}")
        return [ip, "SUCCESS", verify.strip().replace("\n", " | ")]
    except Exception as exc:
        # Any failure (unreachable, bad login, timeout, command error) -> skip
        reason = str(exc).strip().split("\n")[0]
        print(f"[SKIPPED] {ip}: {reason}")
        return [ip, "SKIPPED", reason]


def main():
    ips = ip_range(START_IP, END_IP)
    print(f"Processing {len(ips)} addresses ({START_IP} - {END_IP})...\n")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        results = list(pool.map(configure_switch, ips))

    with open(RESULT_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["IP", "Status", "Details"])
        writer.writerows(results)

    ok = sum(1 for r in results if r[1] == "SUCCESS")
    print(f"\nDone: {ok} configured, {len(results) - ok} skipped. Results saved to {RESULT_FILE}")


if __name__ == "__main__":
    main()