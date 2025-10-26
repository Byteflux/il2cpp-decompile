from ghidra.app.util.cparser.C import CParserUtils

if __name__ == "__main__":
    args = getScriptArgs()
    CParserUtils.parseHeaderFiles([], [args[0]], [], [], currentProgram.getDataTypeManager(), monitor)
