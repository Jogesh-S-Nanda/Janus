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


class Controller(LeafSystem):
    def __init__(self):
        super().__init__()


class Manipulator:
    def __init__(self, urdf_package: str, urdf_loc: str):
        # basic building blocks
        self.builder = DiagramBuilder()
        plant, scene_graph = AddMultibodyPlantSceneGraph(self.builder, time_step=1e-3)
        self.plant = plant
        self.scene_graph = scene_graph
        self.parser = Parser(plant, scene_graph)
        self.is_built = False
        
        # Load the URDF from the filesystem.
        self.index = self._parser_setup(urdf_package, urdf_loc)

        self.plant.WeldFrames(plant.world_frame(), self.plant.GetFrameByName("base_link"))
        self.plant.Finalize()

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

    def build(self, env: "Environment", name : str | None = None):
        # Adds the MeshcatVisualizer and wires it to the SceneGraph.
        env._launch_in_scenario(self)
        
        self.diagram = self.builder.Build()
        if name:
            self.diagram.set_name(name)    
        else:
            self.diagram.set_name("UR5")
        
        self.is_built = True
        

    
    def add_controller(self, controller: Controller):
        pass

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

# Maybe we can make a simulation class later, and put context therein

class Environment:
    def __init__(self):
        self.meshcat = StartMeshcat()
        
    def _launch_in_scenario(self, robot: Manipulator):
        self.visualizer = MeshcatVisualizer.AddToBuilder(robot.builder, robot.scene_graph, self.meshcat)

    def setup_sim(self, robot: Manipulator, q_init):
        if not robot.is_built:
            raise RuntimeError("Cannot start simulation. You must call 'robot.build()' first!")
        self.context = robot.diagram.CreateDefaultContext()

        simulation = Simulation(robot, self)
        simulation.set_initial_conditions(q_init)
        simulation.publish()

        return simulation

    def camera_config(self, camera_position: np.ndarray, target_position: np.ndarray):
        if camera_position.shape != (3,) or target_position.shape != (3,):
            raise ValueError("camera_position and target_position must be a 1D NumPy array with exactly 3 elements")

        self.meshcat.SetTransform(
            "/Cameras/default",
            RigidTransform(camera_position)
        )

        self.meshcat.SetCameraTarget(target_position)


class Simulation:
    def __init__(self, robot: Manipulator, env: Environment):
        self.robot = robot
        self.env = env
        self.context = robot.diagram.CreateDefaultContext()
        self.simulator = Simulator(robot.diagram, self.context)

    def set_initial_conditions(self, q_init):
        plant = self.robot.plant
        plant_context = plant.GetMyMutableContextFromRoot(self.context)
        plant.SetPositions(plant_context, q_init)

    def run(self, duration, running_as_notebook=True):
        self.simulator.set_target_realtime_rate(1.0)
        self.simulator.Initialize()
        self.simulator.AdvanceTo(duration if running_as_notebook else 0.1)

    def publish(self):
        self.robot.diagram.ForcedPublish(self.context)