import time
from pathlib import Path

from pydrake.all import (
    AddMultibodyPlantSceneGraph,
    DiagramBuilder,
    MeshcatVisualizer,
    Parser,
    StartMeshcat,
    Simulator,
    PackageMap, 
    Role, 
    RigidTransform
)
from manipulation import running_as_notebook

from pydrake.geometry import Sphere

# --------------------------------------------------
# URDF
# --------------------------------------------------

ur_description = Path("ur_description").resolve()
urdf_path = ur_description / "urdf" / "ur5.urdf"

builder = DiagramBuilder()

plant, scene_graph = AddMultibodyPlantSceneGraph(
    builder,
    time_step=1e-4,
)

meshcat = StartMeshcat()

meshcat.SetObject(
    "/test_sphere",
    Sphere(0.1)
)

meshcat.SetTransform(
    "/test_sphere",
    RigidTransform([0, 0, 0])
)

print(meshcat.web_url())


parser = Parser(plant, scene_graph)

# Tell Drake where package://ur_description points to.
package_map = PackageMap()
package_map.Add(
    "ur_description",
    str(ur_description)
)
parser.package_map().AddMap(package_map)

# Load the URDF.
model_instances = parser.AddModels(
    file_name=str(urdf_path)
)

print("Models:", model_instances)
print("Bodies:", plant.num_bodies())
print("Frames:", plant.num_frames())


plant.WeldFrames(
    plant.world_frame(),
    plant.GetFrameByName("base_link"),
)

plant.Finalize()

inspector = scene_graph.model_inspector()

print("Proximity geometries:",
      inspector.NumGeometriesWithRole(Role.kProximity))

print("Illustration geometries:",
      inspector.NumGeometriesWithRole(Role.kIllustration))


# --------------------------------------------------
# Meshcat
# --------------------------------------------------

visualizer = MeshcatVisualizer.AddToBuilder(
    builder,
    scene_graph,
    meshcat,
)


# --------------------------------------------------
# Build diagram
# --------------------------------------------------

diagram = builder.Build()
diagram.set_name("plant and scene_graph")


# --------------------------------------------------
# Context
# --------------------------------------------------

diag_context = diagram.CreateDefaultContext()

plant_context = plant.GetMyMutableContextFromRoot(
    diag_context
)

plant.SetPositions(
    plant_context,
    [1.57, -0.66, -1.57, 0, 0, -1.6],
)


# --------------------------------------------------
# Simulation
# --------------------------------------------------
diagram.ForcedPublish(diag_context)

simulator = Simulator(
    diagram,
    diag_context,
)

simulator.set_target_realtime_rate(1.0)

simulator.AdvanceTo(
    10.0 if running_as_notebook else 0.1
)


# Keep Meshcat alive
while True:
    time.sleep(1)
