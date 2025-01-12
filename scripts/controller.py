import argparse
import pathlib
import os
import signal
import time
import psutil
import subprocess
import sys


def start(args):
    processes = find_processes()
    if processes:
        print("bot is already running")
        return
    env = dict(os.environ)
    if args.config:
        env["IVANOV_CONFIG"] = args.config
    main_script = pathlib.Path(args.cwd) / "src" / "main.py"
    executor = subprocess.check_call
    if args.background:
        executor = subprocess.Popen
    executor([sys.executable, main_script], cwd=args.cwd, env=env)


def check_if_target(command_line, cwd):
    if not command_line or len(command_line) <= 1:
        return False
    if "python" not in command_line[0]:
        return False
    script = pathlib.Path(command_line[1])
    if not script.is_absolute():
        script = cwd / script
    assert script.is_absolute()
    script = script.resolve()
    return script.parts[-2:] == ("src", "main.py")


def find_processes():
    processes = []
    for proc in psutil.process_iter(attrs=["pid", "name", "cmdline", "cwd"]):
        if check_if_target(proc.info["cmdline"], proc.info["cwd"]):
            pid = proc.info["pid"]
            p = psutil.Process(pid)
            print(f"found {pid}: {proc.info['cmdline']}")
            processes.append(p)
    return processes


def stop(args):
    processes = find_processes()
    for p in processes:
        print(f"sending stop signal to {p.pid}")
        if sys.platform == "win32":
            p.terminate()
        else:
            p.send_signal(signal.SIGINT)
    for _ in range(20):
        if all(not p.is_running() for p in processes):
            return
        time.sleep(1)
    for pid in processes:
        if p.is_running():
            p.terminate()


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    start_parser = subparsers.add_parser("start")
    start_parser.add_argument(
        "-C", default=pathlib.Path(__file__).parent.parent, dest="cwd"
    )
    start_parser.add_argument("--background", action="store_true")
    start_parser.add_argument("--config")

    stop_parser = subparsers.add_parser("stop")

    args = parser.parse_args()

    if args.command == "start":
        start(args)
    else:
        stop(args)


if __name__ == "__main__":
    main()
