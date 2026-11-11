import subprocess
from datetime import datetime, timedelta

now = datetime.now()
start = now - timedelta(hours=60)

with open("/tmp/normal.log", "w") as f:
    for i in range(3480):
        ts = (start + timedelta(minutes=i)).strftime("%b %e %H:%M:%S")
        f.write(f"{ts} host app[1]: heartbeat {i} ok\n")

with open("/tmp/recent.log", "w") as f:
    for i in range(300):
        ts = (now - timedelta(seconds=i * 5)).strftime("%b %e %H:%M:%S")
        f.write(f"{ts} host app[1]: disk failure on sda\n")


def run(*args):
    subprocess.run(["aether", *args])


run("baseline", "build", "--hours", "72", "--source", "files", "--file", "/tmp/normal.log")
run("scan", "--hours", "1", "--source", "files", "--file", "/tmp/recent.log")
