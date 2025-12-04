"""
Copyright (C) Microsoft Corporation.
Copyright (C) 2025 IAMAI CONSULTING CORP
MIT License.

Demonstrates connecting to a PX4 Drone (for manual QGC control)
AND adds GLOBAL keyboard control (Arrow Keys) for a rover.
INCLUDES: Dual Camera Display (Drone & Rover) with CONNECTION RETRY LOGIC.
"""
import argparse
import sys
import asyncio
import threading
import projectairsim
from projectairsim.utils import projectairsim_log
from projectairsim.image_utils import ImageDisplay 
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

ENGINE_STEP = 0.02
STEER_STEP = 0.05
ENGINE_MIN = -1.0
ENGINE_MAX = 1.0
STEER_MIN = -1.0
STEER_MAX = 1.0

class RoverState:
    def __init__(self):
        self.keys_pressed = set()
        self.running = True

rover_state = RoverState()

def on_press(key):
    rover_state.keys_pressed.add(key)

def on_release(key):
    if key == keyboard.KeyCode.from_char('q'):
        rover_state.running = False
        return False
    if key in rover_state.keys_pressed:
        rover_state.keys_pressed.remove(key)

async def rover_keyboard_loop(rover: projectairsim.Rover):
    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()

    projectairsim_log().info("Rover controls (Global): ARROW KEYS to move, SPACE=brake, Q=quit")

    # Initialize loop variables
    engine = 0.0
    steer = 0.0
    brake = 0.0

    while rover_state.running:
        controls_updated = False
        target_engine = 0.0
        target_steer = 0.0
        new_brake = 0.0

        if Key.up in rover_state.keys_pressed:
            target_engine = 1.0
        elif Key.down in rover_state.keys_pressed:
            target_engine = -1.0
        
        if Key.left in rover_state.keys_pressed:
            target_steer = -1.0
        elif Key.right in rover_state.keys_pressed:
            target_steer = 1.0
            
        if Key.space in rover_state.keys_pressed:
            new_brake = 1.0
            target_engine = 0.0
            target_steer = 0.0

        # Ramping logic
        if engine < target_engine:
            engine = min(engine + ENGINE_STEP, target_engine)
            controls_updated = True
        elif engine > target_engine:
            engine = max(engine - ENGINE_STEP, target_engine)
            controls_updated = True
        
        if steer < target_steer:
            steer = min(steer + STEER_STEP, target_steer)
            controls_updated = True
        elif steer > target_steer:
            steer = max(steer - STEER_STEP, target_steer)
            controls_updated = True

        if brake != new_brake:
            brake = new_brake
            controls_updated = True
            
        if controls_updated or abs(engine) > 0.01 or abs(steer) > 0.01:
            try:
                await rover.set_rover_controls(
                    engine=engine, steering_angle=steer, brake=brake
                )
            except Exception as e:
                pass # Ignore connection blips
        
        await asyncio.sleep(0.02)
    
    listener.stop()
    projectairsim_log().info("Rover teleop: disarming & disabling API control.")
    try:
        await rover.set_rover_controls(engine=0.0, steering_angle=0.0, brake=1.0)
        rover.disarm()
        rover.disable_api_control()
    except:
        pass

def run_rover_async_loop(rover):
    try:
        asyncio.run(rover_keyboard_loop(rover))
    except Exception as e:
        projectairsim_log().error(f"Rover loop exception: {e}", exc_info=True)
        os._exit(1)

# ---------------------- Main / Camera Setup ----------------------

def main():
    parser = argparse.ArgumentParser(description="PX4 Drone + Rover with Dual Camera Feed")
    parser.add_argument("--address", type=str, default="127.0.0.1")
    parser.add_argument("--sceneconfigfile", type=str, default="scene_px4_eolic_park_drone_rover.jsonc")
    parser.add_argument("--simconfigpath", type=str, default="sim_config/")
    parser.add_argument("--topicsport", type=int, default=8989)
    parser.add_argument("--servicesport", type=int, default=8990)
    args = parser.parse_args()

    # --- PHASE 1: LOAD SCENE ---
    projectairsim_log().info(">>> PHASE 1: Connecting to load scene...")
    client_loader = projectairsim.ProjectAirSimClient(
        address=args.address,
        port_topics=args.topicsport,
        port_services=args.servicesport,
    )
    client_loader.connect()
    
    # Load the world (starts the simulator spawning process)
    world = projectairsim.World(
        client=client_loader,
        scene_config_name=args.sceneconfigfile,
        sim_config_path=args.simconfigpath
    )
    
    # --- PHASE 2: WAIT FOR SPAWN ---
    # We must wait long enough for the Rover to fully spawn and register topics
    projectairsim_log().info(">>> PHASE 2: Waiting 8 seconds for robots to spawn...")
    time.sleep(8) 
    
    # Disconnect the loader client to clear any stale topic cache
    projectairsim_log().info(">>> PHASE 3: Reconnecting to refresh topic list...")
    client_loader.disconnect()
    
    # --- PHASE 3: FRESH CONNECTION ---
    # Create a BRAND NEW client instance. This forces it to fetch the topic list 
    # from scratch, which should now include the Rover.
    client = projectairsim.ProjectAirSimClient(
        address=args.address,
        port_topics=args.topicsport,
        port_services=args.servicesport,
    )
    client.connect()

    # We reuse the 'world' object but inject the new client so it stays valid
    world.client = client

    # DEBUG: Print all found topics to verify Rover is there
    # (Note: accessing protected member for debugging purposes)
    if hasattr(client, 'topics_info_list'):
        projectairsim_log().info(f"DEBUG: Found {len(client.topics_info_list)} topics.")
        rover_topics = [t for t in client.topics_info_list if "Rover1" in t.name]
        if not rover_topics:
            projectairsim_log().error("CRITICAL: 'Rover1' topics NOT found in simulator list!")
            projectairsim_log().error("Please check your JSON config files for naming errors.")
        else:
            projectairsim_log().info(f"DEBUG: Verified {len(rover_topics)} topics for Rover1.")

    # 3. Initialize ImageDisplay for Camera Feeds
    image_display = ImageDisplay()

    # ------------------ DRONE SETUP ------------------
    projectairsim_log().info("Initializing Drone1...")
    drone = projectairsim.Drone(client, world, "Drone1")
    
    drone_window = "Drone View"
    image_display.add_chase_cam(drone_window, resize_x=1280, resize_y=720)
    
    if "Chase" in drone.sensors:
        client.subscribe(
            drone.sensors["Chase"]["scene_camera"],
            lambda _, img: image_display.receive(img, drone_window)
        )
    else:
        projectairsim_log().warning("Drone1 'Chase' camera not found! Check connection.")

    # ------------------ ROVER SETUP ------------------
    projectairsim_log().info("Initializing Rover1...")
    
    # Try initializing Rover; if it fails, we catch it to avoid crashing everything
    try:
        rover = projectairsim.Rover(client, world, "Rover1")
        rover_sensors = projectairsim.Drone(client, world, "Rover1")
        
        projectairsim_log().info("Rover: enabling API & arming")
        rover.enable_api_control()
        rover.arm()

        rover_window = "Rover View"
        image_display.add_chase_cam(rover_window, resize_x=1280, resize_y=720)
        
        if hasattr(rover_sensors, 'sensors') and "Chase" in rover_sensors.sensors:
            client.subscribe(
                rover_sensors.sensors["Chase"]["scene_camera"],
                lambda _, img: image_display.receive(img, rover_window)
            )
        else:
            projectairsim_log().warning("Rover1 'Chase' camera not found! (Sensors might be empty)")

        # Start keyboard thread only if Rover init succeeded
        rover_thread = threading.Thread(
            target=run_rover_async_loop,
            args=(rover,),
            daemon=True,
        )
        rover_thread.start()

    except Exception as e:
        projectairsim_log().error(f"Failed to initialize Rover: {e}")
        projectairsim_log().error("Continuing with Drone only...")

    image_display.start()

    # ------------------ MAIN LOOP ------------------
    projectairsim_log().info("================================================================")
    projectairsim_log().info("System Ready.")
    projectairsim_log().info("1. Drone1: Use QGroundControl (QGC) to Fly.")
    projectairsim_log().info("2. Rover1: Click anywhere and use ARROW KEYS.")
    projectairsim_log().info("3. Check the two pop-up windows for camera feeds.")
    projectairsim_log().info("Press 'Q' to quit.")
    projectairsim_log().info("================================================================")

    try:
        while rover_state.running:
            time.sleep(1)
    except KeyboardInterrupt:
        projectairsim_log().info("Exiting...")
        rover_state.running = False
    finally:
        image_display.stop() 
        client.disconnect()
        print("Client disconnected.")

if __name__ == "__main__":
    main()