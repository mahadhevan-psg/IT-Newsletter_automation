import os
import re
import socket
import sys
import threading

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import envfile  # noqa: E402,F401  (reads .env: the same settings as the server, see .env.example)
import uvicorn  # noqa: E402

# ---------------------------------------------------------------- a name on the local network: http://<LOCAL_NAME>.local
# LOCAL_NAME=itmatrix in .env makes this computer answer to "itmatrix.local" (multicast DNS) for the machines on its own subnet.
# LOCAL_IP is only needed when the computer has several network adapters and the wrong address is picked.
def lan_address():
    """This computer's address on the network, or None while there is no network yet. Nothing is sent."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
        except OSError:
            return None
    return None if ip.startswith(("127.", "169.254.")) else ip


def announce(name, port, stop, every=30):
    """Announce name.local until stop is set. Runs beside the server: it waits for the network (the server starts at boot, often
    before the network is ready), follows a changed address, and only ever prints a message if something fails."""
    try:
        from zeroconf import IPVersion, ServiceInfo, Zeroconf
    except ImportError:
        print(f"[name] '{name}.local' is NOT announced: run  venv\\Scripts\\python.exe -m pip install -r requirements.txt", flush=True)
        return
    current, responder, problem = None, None, None
    while True:
        ip = os.environ.get("LOCAL_IP", "").strip() or lan_address()
        if ip != current:
            if responder:
                responder.close()
                responder, current = None, None
            if ip:
                new = None
                try:
                    new = Zeroconf(interfaces=[ip], ip_version=IPVersion.V4Only)
                    new.register_service(ServiceInfo("_http._tcp.local.", f"{name}._http._tcp.local.", addresses=[socket.inet_aton(ip)],
                                                     port=port, properties={"path": "/"}, server=f"{name}.local."))
                    responder, current, problem = new, ip, None
                    print(f"[name] announced: http://{name}.local{'' if port == 80 else f':{port}'}  ->  {ip}", flush=True)
                except Exception as e:                                    # the name must never stop the application
                    if new:
                        new.close()
                    if repr(e) != problem:                                # said once, then retried quietly
                        problem = repr(e)
                        print(f"[name] could not announce '{name}.local' yet ({problem}); trying again", flush=True)
        if stop.wait(every):
            break
    if responder:
        responder.close()                                                 # tells the network the name is gone


def start_announcing(host, port):
    """Start announcing if LOCAL_NAME is set. Returns a function that stops it."""
    name = os.environ.get("LOCAL_NAME", "").strip().lower().removesuffix(".local")
    if not name:
        return lambda: None
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", name):
        print(f"[name] LOCAL_NAME '{name}' is not usable: only letters, digits and hyphens.", flush=True)
        return lambda: None
    if host in ("127.0.0.1", "localhost"):
        print("[name] LOCAL_NAME is set, but HOST=127.0.0.1 lets only this computer in. Set HOST=0.0.0.0 in .env.", flush=True)
        return lambda: None
    stop = threading.Event()
    worker = threading.Thread(target=announce, args=(name, port, stop), daemon=True)
    worker.start()

    def finish():
        stop.set()
        worker.join(5)
    return finish


if __name__ == "__main__":
    # HOST=127.0.0.1 (this computer only) or 0.0.0.0 (everyone on the network); PORT; RELOAD=0 to stop restarting on code changes: all from .env
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    reload = os.environ.get("RELOAD", "1").strip().lower() not in ("0", "false", "no", "off")
    shown = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
    print(f"Starting the IT Matrix server at http://{shown}:{port}")
    print("  /            sign in (everyone starts here)      /newsletter/   newsletter studio (Admin, HoD)")
    print("  /homepage/   faculty: the home page              /portal/       staff portal")
    print("  /diary/      students: placements diary")
    stop_announcing = start_announcing(host, port)
    try:
        uvicorn.run("backend.app:app", host=host, port=port, reload=reload)
    finally:
        stop_announcing()
