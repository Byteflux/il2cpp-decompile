import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryFile
from typing import Optional
from zipfile import ZipFile

BASE_DIR = Path(__file__).parent
DATA_DIR = Path.home() / ".il2cpp-decompile"
VENV_DIR = DATA_DIR / "venv"
APPS_DIR = DATA_DIR / "apps"


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
        print("Could not find GameAssembly.dll")
        sys.exit(1)

    global_metadata_file = next(game_dir.glob("*_Data/il2cpp_data/Metadata/global-metadata.dat"), None)
    if global_metadata_file is None:
        print("Could not find global-metadata.dat")
        sys.exit(1)

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
            "-overwrite",
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
        il2cppdumper_download_url = os.getenv("IL2CPPDECOMPILE_DOWNLOAD_URL_IL2CPPDUMPER")
        if il2cppdumper_download_url is None:
            print("Missing download URL for Il2CppDumper")
            sys.exit(1)

        _download_and_extract(il2cppdumper_download_url, "Il2CppDumper")
        if not il2cppdumper_path.exists():
            print("Could not find Il2CppDumper.exe")
            sys.exit(1)

    config_file = il2cppdumper_path.parent / "config.json"
    config = {}
    if config_file.exists():
        with open(config_file) as f:
            config = json.load(f)
    if "RequireAnyKey" not in config or config["RequireAnyKey"]:
        config["RequireAnyKey"] = False
        with open(config_file, "w") as f:
            json.dump(config, f)

    result = subprocess.run([il2cppdumper_path, *args])
    if result.returncode > 0:
        sys.exit(result.returncode)


def _run_il2cppdumper_header_to_ghidra(work_dir) -> None:
    script_path = APPS_DIR / "Il2CppDumper/il2cpp_header_to_ghidra.py"
    result = subprocess.run([sys.executable, script_path], cwd=work_dir)
    if result.returncode > 0:
        sys.exit(result.returncode)


def _run_ghidra(args: list[str | os.PathLike] = []) -> None:
    java_glob_pattern = "jdk-*/bin/java.exe"
    java_path = next(APPS_DIR.glob(java_glob_pattern), None)
    if java_path is None:
        jdk_download_url = os.getenv("IL2CPPDECOMPILE_DOWNLOAD_URL_JDK")
        if jdk_download_url is None:
            print("Missing download URL for JDK")
            sys.exit(1)

        _download_and_extract(jdk_download_url)
        java_path = next(APPS_DIR.glob(java_glob_pattern), None)
        if java_path is None:
            print("Could not find java.exe")
            sys.exit(1)

    ghidra_glob_pattern = "ghidra_*/support/pyghidraRun.bat"
    ghidra_path = next(APPS_DIR.glob(ghidra_glob_pattern), None)
    if ghidra_path is None:
        ghidra_download_url = os.getenv("IL2CPPDECOMPILE_DOWNLOAD_URL_GHIDRA")
        if ghidra_download_url is None:
            print("Missing download URL for Ghidra")
            sys.exit(1)

        _download_and_extract(ghidra_download_url)
        ghidra_path = next(APPS_DIR.glob(ghidra_glob_pattern), None)
        if ghidra_path is None:
            print("Could not find pyghidraRun.bat")
            sys.exit(1)

    env = os.environ.copy()
    env["JAVA_HOME"] = str(java_path.parent.parent)

    result = subprocess.run([ghidra_path, *args], env=env)
    if result.returncode > 0:
        sys.exit(result.returncode)


def _download_and_extract(url: str, name: Optional[str] = None) -> None:
    import requests

    with TemporaryFile() as f:
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

        f.seek(0)
        with ZipFile(f) as z:
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
        for command in commands:
            result = subprocess.run(command, stdout=subprocess.DEVNULL)
            if result.returncode > 0:
                shutil.rmtree(VENV_DIR, ignore_errors=True)
                sys.exit(result.returncode)

    result = subprocess.run([venv_python, __file__, *sys.argv[1:]])
    sys.exit(result.returncode)


def _load_dotenv():
    from dotenv import load_dotenv

    env_file = DATA_DIR / ".env"
    if not env_file.exists():
        env_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(BASE_DIR / ".env.example", env_file)

    load_dotenv(env_file)


if __name__ == "__main__":
    main()
