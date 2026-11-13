from pathlib import Path

if __package__:
    try:
        from .roboclass import Manipulator, Environment
        from .controllers import InverseDynamics
    except ImportError:  # pragma: no cover - fallback for older direct-execution layouts
        from roboclass import Manipulator, Environment
        from controllers import InverseDynamics
else:
    from roboclass import Manipulator, Environment
    from controllers import InverseDynamics

from pydrake.all import JointSliders, StateInterpolatorWithDiscreteDerivative

import time
import numpy as np

robot_name = "ur5"
urdf_loc = f"urdf/{robot_name}.urdf"
urdf_folder = "ur_description"
urdf_path = Path(urdf_folder).resolve()

gripper_url = "package://drake_models/wsg_50_description/sdf/schunk_wsg_50_with_tip.sdf"
# # Position: [X, Y, Z] in meters relative to world frame
# camera_position = np.array([0.05, 0.0, 0.02])
# # Target: [X, Y, Z] location the camera focuses on (e.g., base of the arm)
# target_position = np.array([0.0, 0.0, 0.3])
# #env.camera_config(camera_position, target_position)

env = Environment()

ur5 = env.addManipulator(urdf_folder, urdf_loc)
gripper = env.addGripper(gripper_url, ur5)
# brick = env.addObject(
#     urdf_loc="package://drake_models/manipulation_station/061_foam_brick.sdf",
#     name="foam_brick",
#     xyz=np.array([0.6, 0.0, 0.05]),   # 5 cm above the table
#     rpy=np.array([0.0, 0.0, 0.0]),
# )
env.finalize_plant()

kp = 50
ki = 2
kd = 10

ur5_controller = ur5.add_controller(env, "InverseDynamics", [kp, ki, kd, False])

# Initial configuration (6 UR5 joints + 2 WSG-50 gripper fingers)
q_init = np.array([0, -0.8, 1.57, 0, 0, 0, 0, 0])

# Add MeshCat JointSliders and convert positions (nq) -> desired state [q, v] (2*nq)
sliders = env.builder.AddSystem(
    JointSliders(env.meshcat, env.plant, initial_value=q_init)
)
desired_state_source = env.builder.AddSystem(
    StateInterpolatorWithDiscreteDerivative(
        env.plant.num_positions(),
        env.plant.time_step(),
        suppress_initial_transient=True,
    )
)
env.builder.Connect(
    sliders.get_output_port(),
    desired_state_source.get_input_port(),
)
env.builder.Connect(
    desired_state_source.get_output_port(),
    ur5_controller.system.get_input_port_desired_state(),
)

env.build()

print("q_init size:", len(q_init))
print("model_instance positions:", ur5.plant.num_positions(ur5.model_instance))
print("full plant positions:", ur5.plant.num_positions())

sim = env.setup_sim(ur5, q_init)

# Run continuously: Simulation.run() paces to real time (1.0x) and publishes the 6 UR5 joints at 50 Hz
sim.run(np.inf)