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
    MeshcatVisualizerParams
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
            self.plant.get_state_output_port(self.model_instance),
            controller.system.get_input_port_estimated_state(),
        )
        env.builder.Connect(
            controller.system.get_output_port_control(), self.plant.get_actuation_input_port()
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

    def addManipulator(self, urdf_package: str, urdf_loc: str):
        # Load the URDF from the filesystem.
        obj_index = self._parser_setup(urdf_package, urdf_loc)
        self.plant.WeldFrames(self.plant.world_frame(), self.plant.GetFrameByName("base_link"))

        robot = Manipulator(self.plant, obj_index)
        return robot

    def finalize_plant(self):
        self.plant.Finalize()
        self.is_finalized = True

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