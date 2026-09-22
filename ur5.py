import numpy as np
import time
from pathlib import Path
    
from pydrake.all import (
    AbstractValue,
    AddMultibodyPlantSceneGraph,
    DiagramBuilder,
    JointSliders,
    LeafSystem,
    MeshcatVisualizer,
    Parser,
    StartMeshcat,
    Simulator,
    MultibodyPlant
)
from pydrake.multibody.parsing import PackageMap
from manipulation import running_as_notebook

ur_description = Path(
    "urdf_files_dataset/urdf_files/ros-industrial/xacro_generated/"
    "universal_robots/ur_description"
).resolve()


builder = DiagramBuilder()
plant, scene_graph = AddMultibodyPlantSceneGraph(builder, time_step=1e-4)
meshcat = StartMeshcat()
parser = Parser(plant, scene_graph)

package_map = PackageMap()
package_map.Add("urdf_files", "/home/samuel/Documents/DrakeSims/urdf_files_dataset/urdf_files")
parser.package_map().AddMap(package_map)


# Load the URDF from the filesystem.
parser.AddModels(
    file_name=str(ur_description / "urdf/ur5.urdf")
)

plant.WeldFrames(plant.world_frame(), plant.GetFrameByName("base_link"))
plant.Finalize()


# Adds the MeshcatVisualizer and wires it to the SceneGraph.
visualizer = MeshcatVisualizer.AddToBuilder(builder, scene_graph, meshcat)

diagram = builder.Build()
diagram.set_name("plant and scene_graph")

diag_context = diagram.CreateDefaultContext()
context = plant.GetMyMutableContextFromRoot(diag_context)
plant.SetPositions(context, [1.57, -0.66, -1.57, 0, 0, -1.6])

#diagram.ForcedPublish(diag_context)

simulator = Simulator(diagram, diag_context)
simulator.set_target_realtime_rate(1.0)
simulator.AdvanceTo(10.0 if running_as_notebook else 0.1)

while True:
    time.sleep(1)