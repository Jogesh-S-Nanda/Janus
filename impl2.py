from pathlib import Path
from roboclass import Manipulator, Environment
from controllers import InverseDynamics

import time
import numpy as np

robot_name = "ur5"
urdf_loc = f"urdf/{robot_name}.urdf"
urdf_folder = "ur_description"
urdf_path = Path(urdf_folder).resolve()

# # Position: [X, Y, Z] in meters relative to world frame
# camera_position = np.array([0.05, 0.0, 0.02])
# # Target: [X, Y, Z] location the camera focuses on (e.g., base of the arm)
# target_position = np.array([0.0, 0.0, 0.3])
# #env.camera_config(camera_position, target_position)

env = Environment()

ur5 = env.addManipulator(urdf_folder, urdf_loc)
env.finalize_plant()

kp = 10
ki = 0.1
kd = 2

iiwa_controller = ur5.add_controller(env, "InverseDynamics", [kp, ki, kd, False])

env.build()

# # Create simulation
q_init = np.array([0, -0.8, 1.57, 0, 0, 0])
x0 = np.hstack((0 *q_init + 1.57, 0 * q_init))
sim = env.setup_sim(ur5, q_init)
iiwa_controller.set_ref(sim, x0)

sim.run(5.0)
#ur5.diagram.ForcedPublish(context)

while True:
    time.sleep(1)
