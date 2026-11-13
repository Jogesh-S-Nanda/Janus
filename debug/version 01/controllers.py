from pydrake.all import InverseDynamicsController 
import numpy as np

class Controller:
    # Base controller wrapper that defines the interface for the robot's digital twin control layer.
    def __init__(self, name: str):
        self.name = name
        self.system = None

    # Subclasses implement how a controller is attached to the robot model within the simulation diagram.
    def build(self, robot: "Manipulator"):
        raise NotImplementedError

class InverseDynamics(Controller):
    # Creates a joint-space inverse-dynamics controller that can drive the robot toward target motion in the twin.
    def __init__(self, kp, ki, kd, name="InverseDynamics"):
        super().__init__(name)

        self.kp = kp
        self.ki = ki
        self.kd = kd

        self.name = name

    # Builds the Drake inverse-dynamics system and wires it to the robot's plant for closed-loop control.
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

    # Sets the desired state for the controller so the digital twin can follow a commanded trajectory.
    def set_ref(self, sim: "Simulation", state_des):
        self.system.get_input_port_desired_state().FixValue(
            self.system.GetMyMutableContextFromRoot(sim.context), state_des
        )