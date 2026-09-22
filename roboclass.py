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
    "urdf_files/ros-industrial/xacro_generated/"
    "universal_robots/ur_description"
).resolve()

class UniversalRobot5Sim:
    def __init__(self):
        pass 

    def speed_init(self):
        builder = DiagramBuilder()
        plant, scene_graph = AddMultibodyPlantSceneGraph(builder, time_step=1e-4)

        parser = Parser(plant, scene_graph)

        package_map = PackageMap()
        package_map.Add("urdf_files", "/home/samuel/Documents/DrakeSims/Janus/urdf_files")
        parser.package_map().AddMap(package_map)

        # Load the URDF from the filesystem.
        parser.AddModels(
            file_name=str(ur_description / "urdf/ur5.urdf")
        )

        plant.WeldFrames(plant.world_frame(), plant.GetFrameByName("base_link"))
        plant.Finalize()

        return builder, scene_graph, plant

    def speed_setup(self, builder, scene_graph, plant, q_init):
        # Adds the MeshcatVisualizer and wires it to the SceneGraph.
        meshcat = StartMeshcat()
        visualizer = MeshcatVisualizer.AddToBuilder(builder, scene_graph, meshcat)

        diagram = builder.Build()
        diagram.set_name("UR5")

        diag_context = diagram.CreateDefaultContext()
        context = plant.GetMyMutableContextFromRoot(diag_context)
        plant.SetPositions(context, q_init)
        return diagram, diag_context

    def run_sim(self, duration, diagram, diag_context):
        simulator = Simulator(diagram, diag_context)
        simulator.set_target_realtime_rate(1.0)
        simulator.AdvanceTo(duration if running_as_notebook else 0.1)