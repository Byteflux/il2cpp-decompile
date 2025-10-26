import typing

from ghidra.app.util.cparser.C import CParserUtils

if typing.TYPE_CHECKING:
    from ghidra.ghidra_builtins import *

if __name__ == "__main__":
    args = getScriptArgs()
    CParserUtils.parseHeaderFiles([], [args[0]], [], [], currentProgram.getDataTypeManager(), monitor)
