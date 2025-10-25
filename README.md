# il2cpp-decompile

A simple wrapper around **Il2CppDumper** and **Ghidra** to automate the process of decompiling Unity IL2CPP games.

Automates the following workflow:
- Copy `GameAssembly.dll` and `global-metadata.dat`
- Run Il2CppDumper
  - Run script to generate `il2cpp_ghidra.h`
- Import `GameAssembly.dll` into a new Ghidra project
  - Parse header file
  - Create functions and labels

[Il2CppDumper](https://github.com/Perfare/Il2CppDumper), [Ghidra](https://github.com/NationalSecurityAgency/ghidra) and [Temurin JDK](https://github.com/adoptium/temurin21-binaries/) are automatically downloaded and installed.

The Python virtual environment and managed dependencies for il2cpp-decompile are stored in `~/.il2cpp-decompile`.

The output directory is `./il2cpp-decompile/{hash}` where hash is an 8-character hex string based on the SHA256 digest of `GameAssembly.dll`.

```
python il2cpp_decompile.py "C:\Program Files (x86)\Steam\steamapps\common\Megabonk"
```

The above command might produce a file tree like below:
```
il2cpp-decompile/5f0ebac6/DummyDll/*
il2cpp-decompile/5f0ebac6/dump.cs
il2cpp-decompile/5f0ebac6/il2cpp.h
il2cpp-decompile/5f0ebac6/il2cpp_ghidra.h
il2cpp-decompile/5f0ebac6/Megabonk/GameAssembly.dll
il2cpp-decompile/5f0ebac6/Megabonk/Megabonk_Data/il2cpp_data/Metadata/global-metadata.dat
il2cpp-decompile/5f0ebac6/Megabonk.gpr
il2cpp-decompile/5f0ebac6/Megabonk.rep/*
il2cpp-decompile/5f0ebac6/script.json
il2cpp-decompile/5f0ebac6/stringliteral.json
```

Ghidra should launch after the project has been imported, analyzed and relevant scripts have completed. Running `python il2cpp-decompile.py` without any other arguments will also launch Ghidra.
