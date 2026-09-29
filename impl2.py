from pathlib import Path
from roboclass import UniversalRobot5Sim, Environment

urdf_loc = "urdf/ur5.urdf"
urdf_folder = "ur_description"
urdf_path = Path(urdf_folder).resolve()

ur5 = UniversalRobot5Sim(urdf_folder, urdf_loc)

print(ur5.plant)