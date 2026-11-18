import platform
import re
import socket
import subprocess

import paramiko


def normalize_mac(mac: str) -> str:
    """
    Validates a MAC address and returns it as AA:BB:CC:DD:EE:FF.
    Accepts any separator (":", "-", ".", none).
    """
    clean_mac = re.sub(r"[^a-fA-F0-9]", "", mac)
    if len(clean_mac) != 12 or len(re.sub(r"[^a-fA-F0-9:\-. ]", "", mac)) != len(mac):
        raise ValueError(
            "Invalid MAC address. Must contain exactly 12 hexadecimal characters."
        )
    return ":".join(clean_mac[i : i + 2] for i in range(0, 12, 2)).upper()


def wake_on_call(mac: str) -> None:
    """
    Sends a Wake-on-LAN magic packet to the specified MAC address.
    """
    mac_bytes = bytes.fromhex(normalize_mac(mac).replace(":", ""))

    sync_stream = b"\xff" * 6
    magic_packet = sync_stream + (mac_bytes * 16)

    broadcast_ip = "255.255.255.255"
    port = 9

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        # Enable broadcasting option on the socket
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        # Send the 102-byte packet out to the local network
        sock.sendto(magic_packet, (broadcast_ip, port))


def shutdown_now(
    ip: str, key_path: str, username: str = "admin", os_type: str = "linux"
) -> None:
    """
    Safely shuts down a remote PC over SSH using a private key file.
    Raises on failure so callers (e.g. the API) can report the error.
    """
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        # key_filename handles RSA, Ed25519 and ECDSA keys.
        ssh.connect(
            hostname=ip,
            username=username,
            key_filename=key_path,
            look_for_keys=False,
            allow_agent=False,
            timeout=10,
        )

        if os_type.lower() == "windows":
            command = "shutdown /s /t 0"
        else:
            # Linux usually requires sudo for shutdown power privileges
            command = "sudo shutdown -h now"

        _, _, stderr = ssh.exec_command(command)

        error_output = stderr.read().decode()
        if error_output:
            raise RuntimeError(f"Shutdown command reported an error: {error_output}")
    finally:
        ssh.close()


def is_host_up(ip: str, count: int = 2, timeout: int = 1) -> bool:
    """
    Checks if a host is online by pinging its IP address.
    Returns True if the host responds, False otherwise.
    """
    op_sys = platform.system().lower()
    param = "-n" if op_sys == "windows" else "-c"
    timeout_param = "-w" if op_sys == "windows" else "-W"

    # Windows timeout is in milliseconds, Linux/macOS is in seconds
    timeout_value = str(timeout * 1000) if op_sys == "windows" else str(timeout)

    # Build the ping command
    command = ["ping", param, str(count), timeout_param, timeout_value, ip]
    process_timeout = (count * timeout) + 2
    try:
        # Run the command and suppress output streams
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=process_timeout,
        )

        # If the return code is 0, the ping was successful (host is up)
        return result.returncode == 0

    except Exception as e:
        print(f"Error executing ping: {e}")
        return False
