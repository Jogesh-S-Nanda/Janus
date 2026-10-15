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
    Context,
    MeshcatVisualizerParams
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
    def __init__(self, plant, model_instance):
        self.plant = plant
        self.model_instance = model_instance

    def bindContext(self, simulation: "Simulation"):
        self.plant_context = self.plant.GetMyMutableContextFromRoot(simulation.context)

    def get_positions(self):
        return self.plant.GetPositions(
            self.plant_context, self.model_instance
        )

    def get_velocities(self):
        return self.plant.GetVelocities(
            self.plant_context, self.model_instance
        )

    def set_positions(self, q):
        self.plant.SetPositions(
            self.plant_context, self.model_instance, q
        )

    def set_velocities(self, v):
        self.plant.SetVelocities(
            self.plant_context, self.model_instance, v
        )

    def set_initial_conditions(self, q_init, v_init=None):
        self.set_positions(q_init)

        if v_init is not None:
            self.set_velocities(v_init)

    def get_state(self):
        q = self.get_positions(self.plant_context)
        v = self.get_velocities(self.plant_context)
        return np.concatenate([q, v])
    
    def add_controller(self, env: "Environment", controller: Controller):
        env.builder.Connect(
            self.plant.get_state_output_port(self.model_instance),
            controller.get_input_port_estimated_state(),
        )
        env.builder.Connect(
            controller.get_output_port_control(), self.plant.get_actuation_input_port()
        )


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
        # basic building blocks
        self.meshcat = StartMeshcat()
        self.builder = DiagramBuilder()

        plant, scene_graph = AddMultibodyPlantSceneGraph(self.builder, time_step=1e-3)
        self.plant = plant
        self.scene_graph = scene_graph
        self.parser = Parser(plant, scene_graph)
        self.visualizer = MeshcatVisualizer.AddToBuilder(self.builder, self.scene_graph, self.meshcat, MeshcatVisualizerParams(
            publish_period=0.01
        ))
        self.is_built = False

    def addManipulator(self, urdf_package: str, urdf_loc: str):
        # Load the URDF from the filesystem.
        obj_index = self._parser_setup(urdf_package, urdf_loc)
        self.plant.WeldFrames(self.plant.world_frame(), self.plant.GetFrameByName("base_link"))

        robot = Manipulator(self.plant, obj_index)
        return robot

    def finalize_plant(self):
        self.plant.Finalize()

    def _parser_setup(self, urdf_package, urdf_loc):
        # create a package map
        package_map = PackageMap()
        urdf_path = Path(urdf_package).resolve()
        package_map.Add(urdf_package, urdf_path)
        self.parser.package_map().AddMap(package_map)
        index = self.parser.AddModels(
            file_name=str(urdf_path / urdf_loc)
        )[0]
        return index

    def build(self, name : str | None = None):
        # Adds the MeshcatVisualizer and wires it to the SceneGraph.
        self.diagram = self.builder.Build()
        if name:
            self.diagram.set_name(name)    
        else:
            self.diagram.set_name("SimEnv")
        
        self.is_built = True

    def setup_sim(self, robot: Manipulator, q_init):
        if not self.is_built:
            raise RuntimeError("Cannot start simulation. You must call 'self.build()' first!")

        # sim can alternatively be set by 

        simulation = Simulation(self)
        robot.bindContext(simulation)
        robot.set_initial_conditions(q_init)
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
    def __init__(self, env: Environment):
        if not env.is_built:
            raise RuntimeError("Cannot start simulation. You must call 'robot.build()' first!")
        
        self.env = env
        self.context = env.diagram.CreateDefaultContext()
        self.simulator = Simulator(env.diagram, self.context)

    def run(self, duration, running_as_notebook=True):
        self.simulator.set_target_realtime_rate(1.0)
        self.simulator.Initialize()
        self.simulator.AdvanceTo(duration if running_as_notebook else 0.1)

    def publish(self):
        self.env.diagram.ForcedPublish(self.context)