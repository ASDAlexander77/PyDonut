for /f "tokens=*" %i in ('uv venv path') do set VENV=%i
cmake -S . -B build -Dpybind11_DIR="%VENV%\share\cmake\pybind11"
