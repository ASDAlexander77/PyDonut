#include <pybind11/pybind11.h>
#include "Device.hpp"

namespace py = pybind11;

PYBIND11_MODULE(_pynri, m) {
    py::class_<Device>(m, "Device")
        .def(py::init<const std::string&>())
        //.def("info", &Device::info)
        ;
}
