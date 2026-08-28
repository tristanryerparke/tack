// pybind11 wrapper exposing a minimal rigid-body assembly API over
// OndselSolver. Rhino keeps the B-reps; only poses, markers, and joints
// cross this boundary.
//
// Python usage:
//   assembly = ondselsolver.Assembly("Assembly1")
//   assembly.add_part("base", (0, 0, 0), (1, 0, 0, 0))
//   assembly.add_part("bolt", (100, 40, 30), (1, 0, 0, 0))
//   assembly.set_fixed("base", True)
//   assembly.add_marker("base", "hole", (10, 5, 0), (1, 0, 0, 0))
//   assembly.add_marker("bolt", "axis", (0, 0, 0), (1, 0, 0, 0))
//   assembly.add_revolute_joint("J1", "base", "hole", "bolt", "axis")
//   assembly.solve()
//   position, quaternion = assembly.get_pose("bolt")

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <map>
#include <string>

#include "ASMTAssembly.h"
#include "ASMTPart.h"
#include "ASMTMarker.h"
#include "ASMTRevoluteJoint.h"
#include "ASMTFixedJoint.h"
#include "ASMTPointInLineJoint.h"
#include "ASMTParallelAxesJoint.h"
#include "ASMTPlanarJoint.h"
#include "ASMTTranslationalJoint.h"

namespace py = pybind11;
using namespace MbD;

namespace {

class PyAssembly {
public:
    explicit PyAssembly(const std::string& name)
        : assemblyName("/" + name)
    {
        assembly = ASMTAssembly::With();
        assembly->setName(name);
        assembly->setPosition3D(0.0, 0.0, 0.0);
        assembly->setRotationMatrix(1, 0, 0, 0, 1, 0, 0, 0, 1);
        assembly->setVelocity3D(0.0, 0.0, 0.0);
        assembly->setOmega3D(0.0, 0.0, 0.0);
    }

    void add_part(
        const std::string& name,
        const std::array<double, 3>& position,
        const std::array<double, 4>& quaternion)
    {
        requireNewPartName(name);

        auto part = ASMTPart::With();
        part->setName(name);
        part->setPosition3D(position[0], position[1], position[2]);
        part->setQuarternions(
            quaternion[0], quaternion[1], quaternion[2], quaternion[3]);
        part->setVelocity3D(0.0, 0.0, 0.0);
        part->setOmega3D(0.0, 0.0, 0.0);
        assembly->addPart(part);
        partsByName[name] = part;
    }

    void set_fixed(const std::string& name, bool fixed)
    {
        auto& part = partNamed(name);
        part->isFixed = fixed;
    }

    void add_marker(
        const std::string& partName,
        const std::string& markerName,
        const std::array<double, 3>& position,
        const std::array<double, 4>& quaternion)
    {
        auto& part = partNamed(partName);

        auto marker = ASMTMarker::With();
        marker->setName(markerName);
        marker->setPosition3D(position[0], position[1], position[2]);
        marker->setQuarternions(
            quaternion[0], quaternion[1], quaternion[2], quaternion[3]);
        part->addMarker(marker);
    }

    void add_revolute_joint(
        const std::string& name,
        const std::string& partI,
        const std::string& markerI,
        const std::string& partJ,
        const std::string& markerJ)
    {
        partNamed(partI);
        partNamed(partJ);

        auto joint = ASMTRevoluteJoint::With();
        joint->setName(name);
        joint->setMarkerI(assemblyName + "/" + partI + "/" + markerI);
        joint->setMarkerJ(assemblyName + "/" + partJ + "/" + markerJ);
        assembly->addJoint(joint);
    }

    void add_fixed_joint(
        const std::string& name,
        const std::string& partI,
        const std::string& markerI,
        const std::string& partJ,
        const std::string& markerJ)
    {
        partNamed(partI);
        partNamed(partJ);

        auto joint = ASMTFixedJoint::With();
        joint->setName(name);
        joint->setMarkerI(assemblyName + "/" + partI + "/" + markerI);
        joint->setMarkerJ(assemblyName + "/" + partJ + "/" + markerJ);
        assembly->addJoint(joint);
    }

    void add_point_in_line_joint(
        const std::string& name,
        const std::string& partI,
        const std::string& markerI,
        const std::string& partJ,
        const std::string& markerJ)
    {
        partNamed(partI);
        partNamed(partJ);

        auto joint = ASMTPointInLineJoint::With();
        joint->setName(name);
        joint->setMarkerI(assemblyName + "/" + partI + "/" + markerI);
        joint->setMarkerJ(assemblyName + "/" + partJ + "/" + markerJ);
        assembly->addJoint(joint);
    }

    void add_translational_joint(
        const std::string& name,
        const std::string& partI,
        const std::string& markerI,
        const std::string& partJ,
        const std::string& markerJ)
    {
        partNamed(partI);
        partNamed(partJ);

        auto joint = ASMTTranslationalJoint::With();
        joint->setName(name);
        joint->setMarkerI(assemblyName + "/" + partI + "/" + markerI);
        joint->setMarkerJ(assemblyName + "/" + partJ + "/" + markerJ);
        assembly->addJoint(joint);
    }

    void add_parallel_axes_joint(
        const std::string& name,
        const std::string& partI,
        const std::string& markerI,
        const std::string& partJ,
        const std::string& markerJ)
    {
        partNamed(partI);
        partNamed(partJ);

        auto joint = ASMTParallelAxesJoint::With();
        joint->setName(name);
        joint->setMarkerI(assemblyName + "/" + partI + "/" + markerI);
        joint->setMarkerJ(assemblyName + "/" + partJ + "/" + markerJ);
        assembly->addJoint(joint);
    }

    void add_planar_joint(
        const std::string& name,
        const std::string& partI,
        const std::string& markerI,
        const std::string& partJ,
        const std::string& markerJ,
        double offset)
    {
        partNamed(partI);
        partNamed(partJ);

        auto joint = ASMTPlanarJoint::With();
        joint->setName(name);
        joint->setMarkerI(assemblyName + "/" + partI + "/" + markerI);
        joint->setMarkerJ(assemblyName + "/" + partJ + "/" + markerJ);
        joint->offset = offset;
        assembly->addJoint(joint);
    }

    void solve()
    {
        assembly->solve();
    }

    void begin_drag()
    {
        assembly->runPreDrag();
    }

    void drag_step(
        const std::vector<std::string>& names,
        const std::vector<std::array<double, 3>>& positions,
        const std::vector<std::array<double, 4>>& quaternions)
    {
        auto dragParts = std::make_shared<std::vector<std::shared_ptr<ASMTPart>>>();
        for (size_t i = 0; i < names.size(); i++) {
            auto& part = partNamed(names[i]);
            part->setPosition3D(
                positions[i][0], positions[i][1], positions[i][2]);
            part->setQuarternions(
                quaternions[i][0],
                quaternions[i][1],
                quaternions[i][2],
                quaternions[i][3]);
            dragParts->push_back(part);
        }
        assembly->runDragStep(dragParts);
    }

    void end_drag()
    {
        assembly->runPostDrag();
    }

    std::pair<std::array<double, 3>, std::array<double, 4>> get_pose(
        const std::string& name) const
    {
        auto& part = partNamed(name);

        double x, y, z;
        double q0, q1, q2, q3;
        part->getPosition3D(x, y, z);
        part->getQuarternions(q0, q1, q2, q3);
        return {{x, y, z}, {q0, q1, q2, q3}};
    }

    std::vector<std::string> part_names() const
    {
        std::vector<std::string> names;
        for (auto& [name, part] : partsByName) {
            names.push_back(name);
        }
        return names;
    }

private:
    void requireNewPartName(const std::string& name) const
    {
        if (partsByName.count(name) != 0) {
            throw std::invalid_argument("duplicate part name: " + name);
        }
        if (name.find('/') != std::string::npos) {
            throw std::invalid_argument("part name must not contain '/': " + name);
        }
    }

    std::shared_ptr<ASMTPart>& partNamed(const std::string& name)
    {
        auto it = partsByName.find(name);
        if (it == partsByName.end()) {
            throw std::invalid_argument("unknown part: " + name);
        }
        return it->second;
    }

    const std::shared_ptr<ASMTPart>& partNamed(const std::string& name) const
    {
        auto it = partsByName.find(name);
        if (it == partsByName.end()) {
            throw std::invalid_argument("unknown part: " + name);
        }
        return it->second;
    }

    std::string assemblyName;
    std::shared_ptr<ASMTAssembly> assembly;
    std::map<std::string, std::shared_ptr<ASMTPart>> partsByName;
};

} // namespace

PYBIND11_MODULE(MOD_NAME, m)
{
    m.doc() = "Minimal OndselSolver assembly-constraint API for Rhino.";

    py::class_<PyAssembly>(m, "Assembly", py::module_local())
        .def(py::init<const std::string&>(), py::arg("name"))
        .def(
            "add_part",
            &PyAssembly::add_part,
            py::arg("name"),
            py::arg("position"),
            py::arg("quaternion"))
        .def(
            "set_fixed",
            &PyAssembly::set_fixed,
            py::arg("name"),
            py::arg("fixed"))
        .def(
            "add_marker",
            &PyAssembly::add_marker,
            py::arg("part"),
            py::arg("name"),
            py::arg("position"),
            py::arg("quaternion"))
        .def(
            "add_revolute_joint",
            &PyAssembly::add_revolute_joint,
            py::arg("name"),
            py::arg("part_i"),
            py::arg("marker_i"),
            py::arg("part_j"),
            py::arg("marker_j"))
        .def(
            "add_fixed_joint",
            &PyAssembly::add_fixed_joint,
            py::arg("name"),
            py::arg("part_i"),
            py::arg("marker_i"),
            py::arg("part_j"),
            py::arg("marker_j"))
        .def(
            "add_point_in_line_joint",
            &PyAssembly::add_point_in_line_joint,
            py::arg("name"),
            py::arg("part_i"),
            py::arg("marker_i"),
            py::arg("part_j"),
            py::arg("marker_j"))
        .def(
            "add_translational_joint",
            &PyAssembly::add_translational_joint,
            py::arg("name"),
            py::arg("part_i"),
            py::arg("marker_i"),
            py::arg("part_j"),
            py::arg("marker_j"))
        .def(
            "add_parallel_axes_joint",
            &PyAssembly::add_parallel_axes_joint,
            py::arg("name"),
            py::arg("part_i"),
            py::arg("marker_i"),
            py::arg("part_j"),
            py::arg("marker_j"))
        .def(
            "add_planar_joint",
            &PyAssembly::add_planar_joint,
            py::arg("name"),
            py::arg("part_i"),
            py::arg("marker_i"),
            py::arg("part_j"),
            py::arg("marker_j"),
            py::arg("offset"))
        .def("solve", &PyAssembly::solve)
        .def("begin_drag", &PyAssembly::begin_drag)
        .def(
            "drag_step",
            &PyAssembly::drag_step,
            py::arg("names"),
            py::arg("positions"),
            py::arg("quaternions"))
        .def("end_drag", &PyAssembly::end_drag)
        .def("get_pose", &PyAssembly::get_pose, py::arg("name"))
        .def("part_names", &PyAssembly::part_names);
}
