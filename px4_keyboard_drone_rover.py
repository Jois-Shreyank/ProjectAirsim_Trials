"""
Copyright (C) Microsoft Corporation.
Copyright (C) 2025 IAMAI CONSULTING CORP
MIT License.

Demonstrates connecting to a PX4 Drone (for manual QGC control)
AND adds GLOBAL keyboard control (Arrow Keys) for a rover.
"""
import argparse
import sys
import asyncio
import threading
import projectairsim
from projectairsim.utils import projectairsim_log
import os
import time

# --- PYNPUT SETUP ---
try:
    from pynput import keyboard
    from pynput.keyboard import Key
except ImportError:
    print("Error: 'pynput' library is required for global keyboard control.")
    print("Please run: pip install pynput")
    sys.exit(1)

# ---------------------- Rover keyboard control ----------------------

ENGINE_STEP = 0.002  # Slightly increased response for arrow keys
STEER_STEP = 0.05
ENGINE_MIN = -1.0
ENGINE_MAX = 1.0
STEER_MIN = -1.0
STEER_MAX = 1.0

# Global state to share between the pynput thread and the asyncio loop
class RoverState:
    def __init__(self):
        self.keys_pressed = set()
        self.running = True

rover_state = RoverState()

def on_press(key):
    """Callback when a key is pressed."""
    rover_state.keys_pressed.add(key)

def on_release(key):
    """Callback when a key is released."""
    if key == keyboard.KeyCode.from_char('q'):
        # Press 'q' to stop everything
        rover_state.running = False
        return False # Stop listener
    
    if key in rover_state.keys_pressed:
        rover_state.keys_pressed.remove(key)

async def rover_keyboard_loop(rover: projectairsim.Rover):
    """
    Async loop that reads the global key state and drives the rover.
    """
    engine = 0.0
    steer = 0.0
    brake = 0.0
    
    # Start the non-blocking keyboard listener
    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()

    projectairsim_log().info(
        "Rover controls (Global): ARROW KEYS to move, SPACE=brake, Q=quit"
    )
    projectairsim_log().info(
        "You can now click on the AirSim window and control the rover!"
    )

    while rover_state.running:
        controls_updated = False
        
        # Calculate target values based on currently held keys
        target_engine = 0.0
        target_steer = 0.0
        new_brake = 0.0

        # Check for specific keys in the set
        # UP ARROW
        if Key.up in rover_state.keys_pressed:
            target_engine = 1.0 # Drive forward
        # DOWN ARROW
        elif Key.down in rover_state.keys_pressed:
            target_engine = -1.0 # Reverse
        
        # LEFT ARROW
        if Key.left in rover_state.keys_pressed:
            target_steer = -1.0 # Full Left
        # RIGHT ARROW
        elif Key.right in rover_state.keys_pressed:
            target_steer = 1.0 # Full Right
            
        # SPACE (Brake)
        if Key.space in rover_state.keys_pressed:
            new_brake = 1.0
            target_engine = 0.0
            target_steer = 0.0

        # Logic: Smoothly ramp values or instant set?
        # For arrow keys, "instant set" usually feels more responsive for games,
        # but we can ramp if we want "heavy" physics. 
        # Here we will ramp purely to keep it smooth.

        # --- Engine Ramping ---
        if engine < target_engine:
            engine = min(engine + ENGINE_STEP, target_engine)
            controls_updated = True
        elif engine > target_engine:
            engine = max(engine - ENGINE_STEP, target_engine)
            controls_updated = True
        
        # --- Steering Ramping ---
        if steer < target_steer:
            steer = min(steer + STEER_STEP, target_steer)
            controls_updated = True
        elif steer > target_steer:
            steer = max(steer - STEER_STEP, target_steer)
            controls_updated = True

        # --- Brake Logic ---
        if brake != new_brake:
            brake = new_brake
            controls_updated = True
            
        # Send controls
        if controls_updated or abs(engine) > 0.01 or abs(steer) > 0.01:
            # We send commands as long as we are moving or changing state
            await rover.set_rover_controls(
                engine=engine, steering_angle=steer, brake=brake
            )
        
        # Short sleep to yield control
        await asyncio.sleep(0.02)
    
    # Cleanup
    listener.stop()
    projectairsim_log().info("Rover teleop: disarming & disabling API control.")
    await rover.set_rover_controls(engine=0.0, steering_angle=0.0, brake=1.0)
    rover.disarm()
    rover.disable_api_control()

def start_rover_keyboard_control(client: projectairsim.ProjectAirSimClient,
                                 world: projectairsim.World,
                                 rover_name: str = "Rover1"):
    """
    Thread entry point: create Rover object, arm it, and run the async keyboard loop.
    """
    try:
        rover = projectairsim.Rover(client, world, rover_name)
        projectairsim_log().info("Rover: enabling API & arming")
        rover.enable_api_control()
        rover.arm()

        asyncio.run(rover_keyboard_loop(rover))
    except Exception as e:
        projectairsim_log().error(f"Rover keyboard control exception: {e}", exc_info=True)
        # Ensure main loop dies if rover thread dies
        os._exit(1) 


# ---------------------- Drone (PX4) Connection ----------------------

def main(client: projectairsim.ProjectAirSimClient, robot_name: str, world: projectairsim.World):
    """
    Initializes the Drone object to establish existence in the sim.
    Does NOT arm or take off, allowing for manual control via QGC.
    """
    
    projectairsim_log().info(f"Initializing {robot_name} for PX4 connection...")
    drone = projectairsim.Drone(client, world, robot_name)

    projectairsim_log().info("================================================================")
    projectairsim_log().info(f"{robot_name} Initialized.")
    projectairsim_log().info("Use QGroundControl (QGC) to Arm and Fly manually.")
    projectairsim_log().info("ROVER CONTROLS: Click the AirSim window and use ARROW KEYS.")
    projectairsim_log().info("Press 'Q' to quit.")
    projectairsim_log().info("================================================================")

    try:
        while rover_state.running:
            time.sleep(1)
    except KeyboardInterrupt:
        print()
        projectairsim_log().info("Exiting...")
        rover_state.running = False
    finally:
        client.disconnect()
        print("Client disconnected.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Connects to a PX4 Drone (for manual QGC flight) and provides GLOBAL keyboard control for a Rover."
        )
    )
    parser.add_argument(
        "--address",
        help=("the IP address of the host running Project AirSim"),
        type=str,
        default="127.0.0.1",
    )
    parser.add_argument(
        "--sceneconfigfile",
        help=(
            'the Project AirSim scene config file to load. '
            'Defaults to "scene_px4_sitl.jsonc" for PX4 compatibility.'
        ),
        type=str,
        default="scene_px4_sitl.jsonc",
    )
    parser.add_argument(
        "--simconfigpath",
        help=(
            'the directory containing Project AirSim config files, '
            'defaults to "sim_config"'
        ),
        type=str,
        default="sim_config/",
    )
    parser.add_argument(
        "--topicsport",
        help=(
            "the TCP/IP port of Project AirSim's topic pub-sub client connection "
            '(see the Project AirSim command line switch "-topicsport")'
        ),
        type=int,
        default=8989,
    )
    parser.add_argument(
        "--servicesport",
        help=(
            "the TCP/IP port of Project AirSim's services client connection "
            '(see the Project AirSim command line switch "-servicessport")'
        ),
        type=int,
        default=8990,
    )
    args = parser.parse_args()

    client = projectairsim.ProjectAirSimClient(
        address=args.address,
        port_topics=args.topicsport,
        port_services=args.servicesport,
    )
    client.connect()
    
    world = projectairsim.World(
        client=client,
        scene_config_name=args.sceneconfigfile,
        sim_config_path=args.simconfigpath,
    )

    # Start rover keyboard teleop in a background thread
    rover_thread = threading.Thread(
        target=start_rover_keyboard_control,
        args=(client, world, "Rover1"),
        daemon=True,
    )
    rover_thread.start()

    main(client, "Drone1", world)