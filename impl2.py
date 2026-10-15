from pathlib import Path
from roboclass import Manipulator, Environment
from pydrake.all import InverseDynamicsController 
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

kp = [10] * ur5.plant.num_positions()
ki = [0.1] * ur5.plant.num_positions()
kd = [2] * ur5.plant.num_positions()

iiwa_controller = env.builder.AddSystem(InverseDynamicsController(ur5.plant, kp, ki, kd, False))
iiwa_controller.set_name("iiwa_controller")

ur5.add_controller(env, iiwa_controller)

env.build()

# # Create simulation
q_init = np.array([0, -0.8, 1.57, 0, 0, 0])
x0 = np.hstack((0 *q_init + 1.57, 0 * q_init))
sim = env.setup_sim(ur5, q_init)


iiwa_controller.GetInputPort("desired_state").FixValue(
    iiwa_controller.GetMyMutableContextFromRoot(sim.context), x0
)


sim.run(5.0)
#ur5.diagram.ForcedPublish(context)



while True:
    time.sleep(1)
