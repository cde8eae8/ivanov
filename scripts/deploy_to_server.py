import argparse
import getpass
import logging
import pathlib
import platform
import select
import shlex
import shutil
import subprocess
import sys
import tempfile
import os
import re
import venv
import zipfile

logger = logging.getLogger(__name__)


def collect_files(project_dir):
    def check_path(abspath: pathlib.Path):
        relpath = abspath.relative_to(project_dir)
        if any(part.startswith(".") for part in relpath.parts):
            return False
        for dir in ("__pycache__",):
            if dir in relpath.parts:
                return False
        for name_regexp in (
            r".*\.py",
            r"requirements\.txt",
            r"requirements-dev\.txt",
            r"VERSION",
        ):
            if re.match(name_regexp, abspath.name):
                return True
        assert False, relpath

    logger.info("collecting files in %s", project_dir)
    selected_files = []
    for root, _, files in os.walk(project_dir):
        for file in files:
            path = pathlib.Path(root, file)
            if check_path(path):
                selected_files.append(path)
    return selected_files


def make_archive(project_root, files, archive_path):
    logging.info("writing archive to %s", archive_path)
    with zipfile.ZipFile(archive_path, "w") as zip:
        for file in files:
            relpath = file.relative_to(project_root)
            zip.write(file, arcname=relpath)


def send_archive_and_script(archive_path, target_dir, ssh):
    logging.info("send archive to remote")
    src_to_dst = [
        (archive_path, target_dir / "archive.zip"),
        (__file__, target_dir / "deploy_to_server.py"),
    ]
    if ssh:
        with SCPClient(ssh.get_transport()) as scp:
            for src, dst in src_to_dst:
                scp.put(src, pathlib.PurePosixPath(dst))
    else:
        for src, dst in src_to_dst:
            shutil.copyfile(src, dst)


def extract_archive(bot_path, archive_path):
    with zipfile.ZipFile(archive_path, "r") as zip:
        zip.extractall(bot_path)


def run_remote_deploy(python_exe, target_dir, ssh):
    logging.info("run remote script")
    if ssh:
        target_dir = pathlib.PurePosixPath(target_dir)
    unpack_command = [
        python_exe,
        target_dir / "deploy_to_server.py",
        "--mode=unpack",
        "--target-dir",
        target_dir,
    ]
    unpack_command = [str(p) for p in unpack_command]
    if ssh:
        assert target_dir.is_absolute()
        transport = ssh.get_transport()
        channel = transport.open_session()
        channel.exec_command(shlex.join(unpack_command))
        logging.info("----- REMOTE OUTPUT: BEGIN -----")
        while True:
            rl, _, _ = select.select([channel], [], [], 1.0)
            if len(rl) > 0:
                # Must be stdout
                text = channel.recv(1024)
                if not text:
                    break
                out = sys.stdout
                out.buffer.write(text)
                out.buffer.flush()
        logging.info("----- REMOTE OUTPUTE: END-----")
    else:
        subprocess.check_call(unpack_command)


def setup_python_environment(bot_dir, env_dir):
    venv.create(env_dir, with_pip=True)
    if platform.system() == "Linux":
        python = env_dir / "bin" / "python"
        pip = env_dir / "bin" / "pip"
    elif platform.system() == "Windows":
        python = env_dir / "scripts" / "python"
        pip = env_dir / "scripts" / "pip"
    subprocess.check_call([pip, "install", "-r", bot_dir / "requirements-dev.txt"])
    return python


def run_tests(python, src_dir):
    subprocess.check_call([python, "-m", "pytest"], cwd=src_dir)


def connect_ssh(target_machine):
    ssh = paramiko.SSHClient()
    logger.info("connecting to %s", target_machine)
    user = None
    host = target_machine
    if "@" in target_machine:
        user, host = target_machine.split("@")
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(hostname=host, username=user)
    except paramiko.ssh_exception.AuthenticationException:
        password = getpass.getpass()
        ssh.connect(hostname=host, username=user, password=password)
    return ssh


def local_main(args):
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = pathlib.Path(temp_dir)
        logging.info("using temporary directory %s", temp_dir)
        version = (args.working_dir / "VERSION").read_text().strip()
        args.target_dir /= f"bot-{version}"
        files = collect_files(args.working_dir)
        archive_path = temp_dir / "archive.zip"
        make_archive(args.working_dir, files, archive_path)
        ssh = None
        if args.target_machine != "localhost":
            ssh = connect_ssh(args.target_machine)
            ssh.exec_command(
                shlex.join(["mkdir", str(pathlib.PurePosixPath(args.target_dir))])
            )
        else:
            args.target_dir.mkdir(exist_ok=True)
        send_archive_and_script(archive_path, args.target_dir, ssh)
        run_remote_deploy(args.python_exe, args.target_dir, ssh)


def remote_main(args):
    bot_dir = args.target_dir.absolute() / "bot"
    venv_dir = bot_dir / ".venv"
    bot_dir.mkdir(exist_ok=False)
    extract_archive(bot_dir, args.target_dir / "archive.zip")
    python = setup_python_environment(bot_dir, venv_dir)
    run_tests(python, bot_dir / "src")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="local", choices=["local", "unpack"])
    parser.add_argument(
        "-C", default=pathlib.Path(__file__).parent.parent, dest="working_dir"
    )
    parser.add_argument("--target-dir", required=True)
    parser.add_argument("--target-machine", default="localhost")
    parser.add_argument("--python-exe", default="python")
    args = parser.parse_args()
    args.target_dir = pathlib.Path(args.target_dir)

    format = "%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d: %(message)s"
    if args.mode == "local":
        format = "[L]" + format
    else:
        format = "[R]" + format
    logging.basicConfig(stream=sys.stdout, format=format, level=logging.INFO)
    logging.info("cwd=%s", pathlib.Path.cwd())

    if args.mode == "unpack":
        remote_main(args)
    else:
        import paramiko
        import paramiko.ssh_exception
        from scp import SCPClient

        local_main(args)
        paramiko.ChannelFile
