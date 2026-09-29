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
    Context
)
from pydrake.multibody.parsing import PackageMap
from manipulation import running_as_notebook
from pydrake.math import RigidTransform, RotationMatrix


"""
UniversalRobot5Sim
│
├── construction
├── package management
├── model loading
├── robot configuration
├── simulation
├── kinematics
└── control

"""

class UniversalRobot5Sim:

    def __init__(self, urdf_package: str, urdf_loc: str, name : str | None = None):

        # basic building blocks
        self.builder = DiagramBuilder()
        plant, scene_graph = AddMultibodyPlantSceneGraph(self.builder, time_step=1e-3)
        self.plant = plant
        self.scene_graph = scene_graph
        self.parser = Parser(plant, scene_graph)
        
        # Load the URDF from the filesystem.
        self.index = self._parser_setup(urdf_package, urdf_loc)

        self.plant.WeldFrames(plant.world_frame(), self.plant.GetFrameByName("base_link"))
        self.plant.Finalize()

        self.diagram = builder.Build()
        if name:
            self.diagram.set_name(name)    
        else:
            self.diagram.set_name("UR5")

    def _parser_setup(self, urdf_package, urdf_loc):
        # create a package map
        package_map = PackageMap()
        urdf_path = Path(urdf_package).resolve()
        package_map.Add(urdf_package, urdf_path)
        self.parser.package_map().AddMap(package_map)
        index = self.parser.AddModels(
            file_name=str(urdf_path / urdf_loc)
        )
        return index

    def build(self, builder, scene_graph, plant, q_init, q_des):
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

        # iiwa_controller.GetInputPort("desired_state").FixValue(
        # iiwa_controller.GetMyMutableContextFromRoot(diag_context), q_des
        # ) 


    def add_controller(self, controller: Controller):
        pass

    def set_initial_conditions(self, robot_context, q_init):
        # Pass in the context attributed to the environment.
        context = self.plant.GetMyMutableContextFromRoot(robot_context)
        self.plant.SetPositions(context, q_init)

class Controller(LeafSystem):
    def __init__(self):
        pass



class Environment:
    def __init__(self, robot: UniversalRobot5Sim):
        self.robot = robot
        self.context = robot.CreateDefaultContext()
        self.simulator = Simulator(robot, context)
        
    def construct(self, builder, scene_graph):
        self.meshcat = StartMeshcat()
        self.visualizer = MeshcatVisualizer.AddToBuilder(builder, scene_graph, meshcat)

    def run_sim(self, duration):
        self.simulator.set_target_realtime_rate(1.0)
        self.simulator.AdvanceTo(duration if running_as_notebook else 0.1)