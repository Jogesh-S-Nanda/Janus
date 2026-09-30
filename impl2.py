from pathlib import Path
from roboclass import Manipulator, Environment
import time
import numpy as np

robot_name = "ur5"
urdf_loc = f"urdf/{robot_name}.urdf"
urdf_folder = "ur_description"
urdf_path = Path(urdf_folder).resolve()

# # Initialize manipulator
# ur5 = Manipulator(urdf_folder, urdf_loc)

# # Create Environment
# env = Environment()

# # Build within environment
# ur5.build(env)

# # Position: [X, Y, Z] in meters relative to world frame
# camera_position = np.array([0.05, 0.0, 0.02])
# # Target: [X, Y, Z] location the camera focuses on (e.g., base of the arm)
# target_position = np.array([0.0, 0.0, 0.3])
# #env.camera_config(camera_position, target_position)

# # Create simulation
# q_init = [0, -0.8, 1.57, 0, 0, 0]
# sim = env.setup_sim(ur5, q_init)
# sim.run(5.0)

ur5 = Manipulator(urdf_folder, urdf_loc)

env = Environment()

ur5.build(env)

context = ur5.diagram.CreateDefaultContext()

ur5.diagram.ForcedPublish(context)

while True:
    time.sleep(1)
