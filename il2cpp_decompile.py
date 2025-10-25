import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent
DATA_DIR = Path.home() / ".il2cpp-decompile"
VENV_DIR = DATA_DIR / "venv"
APPS_DIR = DATA_DIR / "apps"
LOGS_DIR = DATA_DIR / "logs"

_ENV_KEY_DOWNLOAD_URL_IL2CPPDUMPER = "IL2CPPDECOMPILE_DOWNLOAD_URL_IL2CPPDUMPER"
_ENV_KEY_DOWNLOAD_URL_JDK = "IL2CPPDECOMPILE_DOWNLOAD_URL_JDK"
_ENV_KEY_DOWNLOAD_URL_GHIDRA = "IL2CPPDECOMPILE_DOWNLOAD_URL_GHIDRA"

_GLOB_PATTERN_GLOBALMETADATA = "*_Data/il2cpp_data/Metadata/global-metadata.dat"
_GLOB_PATTERN_JAVA = "jdk-*/bin/java.exe"
_GLOB_PATTERN_GHIDRA = "ghidra_*/support/pyghidraRun.bat"

_logger = logging.getLogger(__name__)


def main() -> None:
    if Path(sys.prefix) != VENV_DIR:
        _bootstrap()
        return

    _load_dotenv()

    args = sys.argv[1:]
    if not args:
        _run_ghidra()
        return

    game_dir = Path(args[0])
    game_assembly_file = game_dir / "GameAssembly.dll"
    if game_dir.name == "GameAssembly.dll":
        game_assembly_file = game_dir
        game_dir = game_assembly_file.parent

    if not game_assembly_file.exists():
        raise FileNotFoundError(f"Could not find {game_assembly_file}")

    global_metadata_file = next(game_dir.glob(_GLOB_PATTERN_GLOBALMETADATA), None)
    if global_metadata_file is None:
        raise FileNotFoundError(f"Could not find {game_dir / _GLOB_PATTERN_GLOBALMETADATA}")

    shake = hashlib.shake_256()
    with open(game_assembly_file, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            shake.update(chunk)

    id = shake.hexdigest(4)
    work_dir = Path.cwd() / f"il2cpp-decompile/{id}"
    work_dir.mkdir(parents=True, exist_ok=True)

    project_file = work_dir / f"{game_dir.name}.gpr"
    if project_file.exists():
        _run_ghidra([project_file])
        return

    for file in [game_assembly_file, global_metadata_file]:
        dest_file = work_dir / file.relative_to(game_dir.parent)
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file, dest_file)

    game_assembly_file = work_dir / game_assembly_file.relative_to(game_dir.parent)
    global_metadata_file = work_dir / global_metadata_file.relative_to(game_dir.parent)

    _run_il2cppdumper([game_assembly_file, global_metadata_file, work_dir])
    _run_il2cppdumper_header_to_ghidra(work_dir)

    _run_ghidra(
        [
            "--headless",
            work_dir,
            game_dir.name,
            "-import",
            game_assembly_file,
            "-scriptPath",
            f"{BASE_DIR / 'scripts'};{APPS_DIR / 'Il2CppDumper'}",
            "-postScript",
            "parse_header.py",
            work_dir / "il2cpp_ghidra.h",
            "-postScript",
            "ghidra_with_struct.py",
            work_dir / "script.json",
        ]
    )

    _run_ghidra([project_file])


def _run_il2cppdumper(args: list[str | os.PathLike]) -> None:
    il2cppdumper_path = APPS_DIR / "Il2CppDumper/Il2CppDumper.exe"
    if not il2cppdumper_path.exists():
        download_url = os.getenv(_ENV_KEY_DOWNLOAD_URL_IL2CPPDUMPER)
        if download_url is None:
            raise KeyError(f"Missing download URL for Il2CppDumper: {_ENV_KEY_DOWNLOAD_URL_IL2CPPDUMPER}")

        _download_and_extract(download_url, "Il2CppDumper")
        if not il2cppdumper_path.exists():
            raise FileNotFoundError(f"Could not find {il2cppdumper_path}")

    config_file = il2cppdumper_path.parent / "config.json"
    config = {}
    if config_file.exists():
        with open(config_file) as f:
            config = json.load(f)
    if "RequireAnyKey" not in config or config["RequireAnyKey"]:
        config["RequireAnyKey"] = False
        with open(config_file, "w") as f:
            json.dump(config, f)

    subprocess.run([il2cppdumper_path, *args], check=True)


def _run_il2cppdumper_header_to_ghidra(work_dir) -> None:
    script_path = APPS_DIR / "Il2CppDumper/il2cpp_header_to_ghidra.py"
    subprocess.run([sys.executable, script_path], cwd=work_dir, check=True)


def _run_ghidra(args: list[str | os.PathLike] = []) -> None:
    try:
        java_path = _get_file_from_glob(APPS_DIR, _GLOB_PATTERN_JAVA)
    except FileNotFoundError:
        download_url = os.getenv(_ENV_KEY_DOWNLOAD_URL_JDK)
        if download_url is None:
            raise KeyError(f"Missing download URL for JDK: {_ENV_KEY_DOWNLOAD_URL_JDK}")
        _download_and_extract(download_url)
        java_path = _get_file_from_glob(APPS_DIR, _GLOB_PATTERN_JAVA)

    try:
        ghidra_path = _get_file_from_glob(APPS_DIR, _GLOB_PATTERN_GHIDRA)
    except FileNotFoundError:
        download_url = os.getenv(_ENV_KEY_DOWNLOAD_URL_GHIDRA)
        if download_url is None:
            raise KeyError(f"Missing download URL for Ghidra: {_ENV_KEY_DOWNLOAD_URL_GHIDRA}")
        _download_and_extract(download_url)
        ghidra_path = _get_file_from_glob(APPS_DIR, _GLOB_PATTERN_GHIDRA)

    env = os.environ.copy()
    env["JAVA_HOME"] = str(java_path.parent.parent)

    subprocess.run([ghidra_path, *args], env=env, check=True)


def _get_file_from_glob(base_dir: Path, pattern: str) -> Path:
    file = next(base_dir.glob(pattern), None)
    if file is None:
        raise FileNotFoundError(f"Could not find {base_dir / pattern}")
    return file


def _download_and_extract(url: str, name: Optional[str] = None) -> None:
    import requests

    with tempfile.TemporaryFile() as f:
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

        f.seek(0)
        with zipfile.ZipFile(f) as z:
            if name is not None:
                z.extractall(APPS_DIR / name)
            else:
                z.extractall(APPS_DIR)


def _bootstrap() -> None:
    venv_python = VENV_DIR / "Scripts/python.exe"
    if not venv_python.exists():
        shutil.rmtree(VENV_DIR, ignore_errors=True)
        commands: list[list[str | Path]] = [
            [sys.executable, "-m", "venv", VENV_DIR],
            [venv_python, "-m", "pip", "install", "-U", "pip"],
            [venv_python, "-m", "pip", "install", "-r", BASE_DIR / "requirements.txt"],
        ]
        try:
            for command in commands:
                subprocess.run(command, stdout=subprocess.DEVNULL, check=True)
        except:
            shutil.rmtree(VENV_DIR, ignore_errors=True)
            raise

    subprocess.run([venv_python, __file__, *sys.argv[1:]], check=True)


def _load_dotenv() -> None:
    from dotenv import load_dotenv

    env_file = DATA_DIR / ".env"
    if not env_file.exists():
        env_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(BASE_DIR / ".env.example", env_file)

    load_dotenv(env_file)


def _configure_logging() -> Path:
    log_file = LOGS_DIR / f"{time.strftime('%Y-%m-%d')}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=log_file, level=logging.WARNING)
    return log_file


if __name__ == "__main__":
    log_file = _configure_logging()

    try:
        main()
    except Exception as e:
        _logger.error(e, exc_info=True)

        print(f"Error: {e} ({e.__class__.__name__})")
        print(f"Detailed error info has been logged to {log_file}")

        if isinstance(e, OSError):
            sys.exit(e.errno)
        elif isinstance(e, subprocess.CalledProcessError):
            sys.exit(e.returncode)
        else:
            sys.exit(1)
