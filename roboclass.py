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
    Context,
    MeshcatVisualizerParams,
    ModelInstanceIndex
)
from pydrake.multibody.parsing import PackageMap
from manipulation import running_as_notebook
from pydrake.math import RigidTransform, RotationMatrix
from controllers import InverseDynamics, Controller

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

class Manipulator:
    def __init__(self, plant, model_instance: ModelInstanceIndex):
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
            self.plant_context, q
        )

    """
    you are controlling the plant as a whole with InverseDynamics, how do you fix this?
    """

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

    def get_ee_frame(self):
        """Returns the terminal end-effector frame of the manipulator."""
        body_indices = self.plant.GetBodyIndices(self.model_instance)
        if not body_indices:
            raise RuntimeError(f"Model instance {self.model_instance} contains no bodies!")
        
        return self.plant.get_body(body_indices[-1]).body_frame()


    def add_controller(self, env, ctrl_name, params):
        if env.is_built:
            raise RuntimeError("The environment is already built.")

        if not env.is_finalized:
            raise RuntimeError("Finalize the plant first.")

        if ctrl_name == "InverseDynamics":
            kp, ki, kd, has_reference_acceleration = params

            controller = InverseDynamics(
                kp, ki, kd, has_reference_acceleration
            )
        else:
            raise ValueError(f"Unknown controller type: {ctrl_name}")

        controller.build(self)
        controller.system.set_name(ctrl_name)
        env.builder.AddSystem(controller.system)
        # Connect the appropriate ports here.
        env.builder.Connect(
            self.plant.get_state_output_port(),          # no model_instance
            controller.system.get_input_port_estimated_state(),
        )
        env.builder.Connect(
            controller.system.get_output_port_control(),
            self.plant.get_actuation_input_port(),       # no model_instance
        )
        self.controller = controller

        return controller

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
        self.is_finalized = False

    
    def _parser_setup(self, urdf_loc, urdf_package=None):
        # create a package map if the map is given
        if urdf_package:
            package_map = PackageMap()
            urdf_path = Path(urdf_package).resolve()
            package_map.Add(urdf_package, urdf_path)
            self.parser.package_map().AddMap(package_map)
            index = self.parser.AddModels(
                file_name=str(urdf_path / urdf_loc)
            )[0]

        #or else uses the url
        else: 
            index = self.parser.AddModels(url=urdf_loc)[0]
        
        return index

    def get_model_base_frame(self, model_index: ModelInstanceIndex):
        """
        Finds and returns the base Frame object for any loaded model instance.
        Raises an error if the model contains no bodies.
        """
        body_indices = self.plant.GetBodyIndices(model_index)
        
        if not body_indices:
            raise RuntimeError(f"Model instance {model_index} contains no links/bodies!")
            
        # Safely extract the frame object of the first topological body
        return self.plant.get_body(body_indices[0]).body_frame()


    def addManipulator(self, urdf_package: str, urdf_loc: str):
        # Load the URDF from the filesystem.
        obj_index = self._parser_setup(urdf_loc, urdf_package)
        robot_base_frame = self.get_model_base_frame(obj_index)
        self.plant.WeldFrames(self.plant.world_frame(), robot_base_frame)

        robot = Manipulator(self.plant, obj_index)
        return robot

    def addGripper(self, urdf_loc: str, robot: Manipulator):
        obj_index = self._parser_setup(urdf_loc)
        gripper_base_frame = self.get_model_base_frame(obj_index)

        if robot.model_instance is None:
            raise AttributeError("There is no robot to attach to!")
        

        # Weld the gripper to the arm
        self.plant.WeldFrames(robot.get_ee_frame(), gripper_base_frame)

            
        return obj_index

    def addObject(self, urdf_loc: str, name: str = "object",
                xyz: np.ndarray = np.zeros(3),
                rpy: np.ndarray = np.zeros(3)):
        """
        Add a free-floating object to the plant.

        Args:
            urdf_loc: path to URDF/SDF/mesh file.
            name:     name for the model instance (for later lookup).
            xyz:      initial world position [m].
            rpy:      initial world orientation as roll-pitch-yaw [rad].

        Returns:
            Model instance index of the added object.
        """
        if self.plant.is_finalized():
            raise RuntimeError("Cannot add object after plant.Finalize().")

        obj_index = self._parser_setup(urdf_loc)
        self.plant.SetModelInstanceName(obj_index, name)

        # The object should be a free body: pick its first (root) body
        body_indices = self.plant.GetBodyIndices(obj_index)
        if len(body_indices) == 0:
            raise RuntimeError(f"Object '{name}' has no bodies — bad URDF?")

        X_WO = RigidTransform(RollPitchYaw(rpy).ToRotationMatrix(), xyz)
        self.plant.SetDefaultFreeBodyPose(
            self.plant.get_body(body_indices[0]), X_WO
        )

        return obj_index

    def finalize_plant(self):
        self.plant.Finalize()
        self.is_finalized = True

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


"""

import threading
import time

class MyRobotSimulation:
    def __init__(self):
        # Setup Drake diagram, plant, context, and simulator here...
        self.simulator = Simulator(diagram)
        self.context = self.simulator.get_mutable_context()
        self.is_running = False

    def _network_stream_loop(self):
        # This runs on a separate thread
        while self.is_running:
            # Safely grab the current state out of the active context
            state = self.plant.GetPositions(self.plant_context)
            
            # Send 'state' over UDP/TCP socket to Unity here...
            
            time.sleep(0.033) # Control your broadcast rate (e.g., 30 Hz)

    def start_simulation(self, duration):
        self.is_running = True
        
        # 1. Start the streaming thread simultaneously
        stream_thread = threading.Thread(target=self._network_stream_loop)
        stream_thread.start()
        
        try:
            # 2. Hand over control to Drake's solver loop
            self.simulator.AdvanceTo(duration)
        finally:
            # 3. Clean up the thread when AdvanceTo finishes
            self.is_running = False
            stream_thread.join()

"""

