from roboclass import UniversalRobot5Sim
import time

UR5 = UniversalRobot5Sim()

builder, scene_graph, plant = UR5.speed_init()
diagram, diag_context = UR5.speed_setup(builder, scene_graph, plant, [1.57, -0.66, -1.57, 0, 0, -1.6])
UR5.run_sim(10, diagram, diag_context)

while True:
    time.sleep(1)