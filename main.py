from src import pydonut as pyd

if __name__ == "__main__":
    print(pyd.hello())

    pyd.get_graphics_api_from_command_line(["--api", "vulkan"])