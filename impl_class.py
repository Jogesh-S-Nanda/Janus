from roboclass import (
    Manipulator, 
    InverseDynamicsController, 
    MeshcatVisualizer, 
    StartMeshcat,
    RigidTransform,
    Simulator,
)

import numpy as np
import time
from manipulation.utils import RenderDiagram
from pathlib import Path

robot_name = "ur5"
urdf_loc = f"urdf/{robot_name}.urdf"
urdf_folder = "ur_description"
urdf_path = Path(urdf_folder).resolve()

UR5 = Manipulator(urdf_folder, urdf_loc)

# Setup simple diagram without controller
meshcat = StartMeshcat()
visualizer = MeshcatVisualizer.AddToBuilder(UR5.builder, UR5.scene_graph, meshcat)

# Position: [X, Y, Z] in meters relative to world frame
camera_position = [0.05, 0.0, 0.02]
meshcat.SetTransform("/Cameras/default", RigidTransform(camera_position))

# Target: [X, Y, Z] location the camera focuses on (e.g., base of the arm)
target_position = [0.0, 0.0, 0.3]

# 2. Calculate the rotation matrix pointing from camera_position to target_position
# R_WC aligns camera -Z axis toward target, +Y axis up
meshcat.SetCameraTarget([0.0, 0.0, 0.3]) 
diagram = UR5.builder.Build()

diag_context = diagram.CreateDefaultContext()
plant_context = UR5.plant.GetMyMutableContextFromRoot(diag_context)

# Set non-zero elbow position so arm doesn't start in a singular vertical pose
UR5.plant.SetPositions(plant_context, [0, -0.8, 1.57, 0, 0, 0])

simulator = Simulator(diagram, diag_context)
simulator.set_target_realtime_rate(1.0)
simulator.Initialize()

# Check positions before and after
print("q initial:", UR5.plant.GetPositions(plant_context))
simulator.AdvanceTo(6.0)
print("q after 2s gravity fall:", UR5.plant.GetPositions(plant_context))
# q_init = [1.57, -0.66, 1.57, 0, 0, -1.6]
# qdes = np.array([-1.57, 0.1, 0, -1.2, 0, 1.6])
# xdes = np.hstack((qdes, 0 * qdes))
# diagram, diag_context = UR5.speed_setup(builder, scene_graph, plant, q_init, xdes)
# UR5.run_sim(30, diagram, diag_context)

# RenderDiagram(diagram)

while True:
    time.sleep(1)