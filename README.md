# Control Plane

A Python backend (FastAPI) with a small web page for powering hosts on and off: it sends magic packets to perform **Wake-on-LAN**, or connects over **SSH** and runs the `shutdown` command.

## Usage

1. Create a user:
   ```bash
   uv run create_user.py <username>
   ```
2. Run the app:
   ```bash
   uv run fastapi dev main.py
   ```
3. Log in on the web page at http://127.0.0.1:8000.
4. Select a host to see its current status, then choose **Wake** or **Shutdown**.

## Shutdown setup

1. Create a user on the host for the app to log in as.
2. Create a key pair, copy the public key to the host, and export the private key path in the current environment:
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/control_plane_key
   ssh-copy-id -i ~/.ssh/control_plane_key.pub <user>@<host>
   export CONTROL_PLANE_SSH_KEY=~/.ssh/control_plane_key
   ```
3. Give that user passwordless permission to run `shutdown`. On Linux, add this entry with `sudo visudo`:
   ```
   <user> ALL=(ALL) NOPASSWD: /sbin/shutdown
   ```
   Check the path with `command -v shutdown`; on some distros it is `/usr/sbin/shutdown`. Windows hosts don't need this step.

## Wake-on-LAN setup

- Make sure you have the host's MAC address.
- Enable Wake-on-LAN in the host's UEFI/BIOS.
- Run the app on the same local network as the host, since magic packets are broadcast and don't cross routers.

## License

Released under the [MIT License](LICENSE).
