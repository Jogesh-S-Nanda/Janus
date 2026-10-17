from pydrake.all import InverseDynamicsController 
import numpy as np

class Controller:
    def __init__(self, name: str):
        self.name = name
        self.system = None

    def build(self, robot: "Manipulator"):
        raise NotImplementedError

class InverseDynamics(Controller):
    def __init__(self, kp, ki, kd, name="InverseDynamics"):
        super().__init__(name)

        self.kp = kp
        self.ki = ki
        self.kd = kd

        self.name = name

    def build(self, robot: "Manipulator"):
        plant = robot.plant

        nq = plant.num_positions()   

        kp = np.broadcast_to(self.kp, nq).copy()
        ki = np.broadcast_to(self.ki, nq).copy()
        kd = np.broadcast_to(self.kd, nq).copy()

        self.system = InverseDynamicsController(
            plant,
            kp,
            ki,
            kd,
            False
        )

        return self.system

    def set_ref(self, sim: "Simulation", state_des):
        self.system.get_input_port_desired_state().FixValue(
            self.system.GetMyMutableContextFromRoot(sim.context), state_des
        )