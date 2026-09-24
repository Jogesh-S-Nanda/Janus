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
    MultibodyPlant, 
    InverseDynamicsController, 
    RotationMatrix
)
from pydrake.multibody.parsing import PackageMap
from manipulation import running_as_notebook
from pydrake.math import RigidTransform, RotationMatrix


ur_description = Path(
    "urdf_files/ros-industrial/xacro_generated/"
    "universal_robots/ur_description"
).resolve()

class Environment:
    def __init__(self, robot, context):
        self.robot = robot
        self.context = context

    def build(self):
        meshcat = StartMeshcat()
        visualizer = MeshcatVisualizer.AddToBuilder(builder, scene_graph, meshcat)


class UniversalRobot5Sim:
    def __init__(self):
        pass 

    def speed_init(self):
        builder = DiagramBuilder()
        plant, scene_graph = AddMultibodyPlantSceneGraph(builder, time_step=1e-3)

        parser = Parser(plant, scene_graph)

        package_map = PackageMap()
        package_map.Add("urdf_files", "/home/samuel/Documents/DrakeSims/Janus/urdf_files")
        parser.package_map().AddMap(package_map)

        # Load the URDF from the filesystem.
        manipul = parser.AddModels(
            file_name=str(ur_description / "urdf/ur5.urdf")
        )

        plant.WeldFrames(plant.world_frame(), plant.GetFrameByName("base_link"))
        plant.Finalize()

        return builder, scene_graph, plant, manipul

    def speed_setup(self, builder, scene_graph, plant, q_init, q_des):
        # Adds the MeshcatVisualizer and wires it to the SceneGraph.
        

        # Position: [X, Y, Z] in meters relative to world frame
        camera_position = [0.05, 0.0, 0.02]
        meshcat.SetTransform("/Cameras/default", RigidTransform(camera_position))

        # Target: [X, Y, Z] location the camera focuses on (e.g., base of the arm)
        target_position = [0.0, 0.0, 0.3]

        # 2. Calculate the rotation matrix pointing from camera_position to target_position
        # R_WC aligns camera -Z axis toward target, +Y axis up
        meshcat.SetCameraTarget([0.0, 0.0, 0.3])   

        # kp = plant.num_positions() * [50]
        # kd= plant.num_positions() * [20]
        # ki = plant.num_positions() * [1]

        # iiwa_controller = builder.AddSystem(InverseDynamicsController(plant, np.array(kp), np.array(ki), np.array(kd), False))
        # iiwa_controller.set_name("iiwa_controller")
        # builder.Connect(
        #     plant.get_state_output_port(),
        #     iiwa_controller.get_input_port_estimated_state(),
        # )
        # builder.Connect(
        #     iiwa_controller.get_output_port_control(), plant.get_actuation_input_port()
        # )

        diagram = builder.Build()
        diagram.set_name("UR5")

        diag_context = diagram.CreateDefaultContext()
        context = plant.GetMyMutableContextFromRoot(diag_context)
        plant.SetPositions(context, q_init)
        # iiwa_controller.GetInputPort("desired_state").FixValue(
        # iiwa_controller.GetMyMutableContextFromRoot(diag_context), q_des
        # ) 
        return diagram, diag_context

    def run_sim(self, duration, diagram, diag_context):
        simulator = Simulator(diagram, diag_context)
        simulator.set_target_realtime_rate(1.0)
        simulator.AdvanceTo(duration if running_as_notebook else 0.1)


class Controller(LeafSystem):
    def __init__(self):
        pass