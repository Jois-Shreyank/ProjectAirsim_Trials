import argparse
import projectairsim
from projectairsim.utils import projectairsim_log
import time
import pprint

def main():
    parser = argparse.ArgumentParser(description="Inspect Drone vs Rover Object Internals")
    parser.add_argument("--address", type=str, default="127.0.0.1")
    parser.add_argument("--sceneconfigfile", type=str, default="scene_px4_eolic_park_drone_rover.jsonc")
    parser.add_argument("--simconfigpath", type=str, default="sim_config/")
    parser.add_argument("--topicsport", type=int, default=8989)
    parser.add_argument("--servicesport", type=int, default=8990)
    args = parser.parse_args()

    # --- PHASE 1: LOAD & WAIT ---
    projectairsim_log().info(">>> PHASE 1: Loading Scene...")
    client_loader = projectairsim.ProjectAirSimClient(
        address=args.address, port_topics=args.topicsport, port_services=args.servicesport
    )
    client_loader.connect()
    world = projectairsim.World(
        client=client_loader, scene_config_name=args.sceneconfigfile, sim_config_path=args.simconfigpath
    )
    
    projectairsim_log().info(">>> Waiting 8 seconds for Rover spawn...")
    time.sleep(8)
    client_loader.disconnect()

    # --- PHASE 2: INSPECT ---
    projectairsim_log().info(">>> PHASE 2: Fresh Connection & Inspection...")
    client = projectairsim.ProjectAirSimClient(
        address=args.address, port_topics=args.topicsport, port_services=args.servicesport
    )
    client.connect()
    world.client = client # Update world with new client

    # Initialize Objects
    drone = projectairsim.Drone(client, world, "Drone1")
    rover = projectairsim.Drone(client, world, "Rover1")

    print("\n" + "="*40)
    print("      COMPARISON: DRONE vs ROVER")
    print("="*40)

    # 1. Compare 'sensors' attribute
    print(f"\n[Drone1] .sensors keys: {list(drone.sensors.keys()) if hasattr(drone, 'sensors') else 'NO ATTRIBUTE'}")
    print(f"[Rover1] .sensors keys: {list(rover.sensors.keys()) if hasattr(rover, 'sensors') else 'NO ATTRIBUTE'}")

    # 2. Print Raw Object Dictionaries (Filtered)
    # We filter out private attributes (starting with _) to make it readable
    print("\n" + "-"*20 + " ROVER OBJECT CONTENT " + "-"*20)
    rover_dict = {k: v for k, v in rover.__dict__.items() if not k.startswith('_')}
    pprint.pprint(rover_dict)

    print("\n" + "-"*20 + " CLIENT TOPIC SEARCH " + "-"*20)
    # 3. Search Client Topics for ANYTHING related to Rover1
    # This proves if the simulator is sending data, even if the Rover object missed it.
    rover_topics = []
    if hasattr(client, 'topics'):
        for key in client.topics.keys():
            if "Rover" in key:
                rover_topics.append(key)
    
    if len(rover_topics) > 0:
        print(f"FOUND {len(rover_topics)} TOPICS MATCHING 'Rover':")
        for t in sorted(rover_topics):
            print(f" - {t}")
    else:
        print("CRITICAL: Client has ZERO topics matching 'Rover'.")

    client.disconnect()

if __name__ == "__main__":
    main()