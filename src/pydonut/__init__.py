from pydonut._core import hello_from_bin
from pydonut._pydonut import GetGraphicsAPIFromCommandLine

def hello() -> str:
    return hello_from_bin()

def get_graphics_api_from_command_line(args: list[str]) -> int:
    return GetGraphicsAPIFromCommandLine(args)