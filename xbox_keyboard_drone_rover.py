"""
Copyright (C) Microsoft Corporation.
Copyright (C) 2025 IAMAI CONSULTING CORP
MIT License.

Demonstrates using an Xbox controller as a remote control for SimpleFlight
AND adds keyboard control for a rover.
"""
import argparse
import sys
import asyncio
import threading
import msvcrt  # Windows-only

import projectairsim
import projectairsim.rc
from projectairsim.utils import projectairsim_log


# ---------------------- Rover keyboard control ----------------------

ENGINE_STEP = 0.1
STEER_STEP = 0.15
ENGINE_MIN = -1.0
ENGINE_MAX = 1.0
STEER_MIN = -1.0
STEER_MAX = 1.0


async def rover_keyboard_loop(rover: projectairsim.Rover):
    """
    Async loop that drives the rover using keyboard input.

    Controls:
      W/S -> throttle up/down (engine)
      A/D -> steer left/right
      SPACE -> full brake, engine 0
      0 -> release brake, center steering, engine 0
      Q -> quit rover teleop
    """
    engine = 0.0
    steer = 0.0
    brake = 0.0
    running = True

    projectairsim_log().info(
        "Rover keyboard controls: W/S=throttle, A/D=steer, SPACE=brake, 0=reset, Q=quit"
    )

    while running:
        if msvcrt.kbhit():
            key = msvcrt.getch()

            if key in (b"w", b"W"):
                brake = 0.0
                engine = min(engine + ENGINE_STEP, ENGINE_MAX)

            elif key in (b"s", b"S"):
                brake = 0.0
                engine = max(engine - ENGINE_STEP, ENGINE_MIN)

            elif key in (b"a", b"A"):
                steer = max(steer - STEER_STEP, STEER_MIN)

            elif key in (b"d", b"D"):
                steer = min(steer + STEER_STEP, STEER_MAX)

            elif key == b" ":
                # full brake, stop engine
                brake = 1.0
                engine = 0.0

            elif key == b"0":
                # reset steering & brake, engine 0
                brake = 0.0
                steer = 0.0
                engine = 0.0

            elif key in (b"q", b"Q"):
                projectairsim_log().info("Rover teleop: Q pressed, stopping.")
                running = False
                continue

            # send new controls
            task = await rover.set_rover_controls(
                engine=engine, steering_angle=steer, brake=brake
            )
            await task

        await asyncio.sleep(0.05)

    # tidy shutdown of rover API control
    projectairsim_log().info("Rover teleop: disarming & disabling API control.")
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


# ---------------------- Drone (Xbox) control ----------------------


def main(
    client: projectairsim.ProjectAirSimClient, robot_name: str, rc_config_file: str
):
    """
    Connect an Xbox game controller as the remote control for the
    Simple Flight flight controller by pairing instances of the
    XboxInputControllerSF and SimpleFlightRC classes.

    This version keeps the original behavior for the drone and assumes
    a separate thread is running rover keyboard control.
    """
    simple_flight_rc = None

    # Create the RC configuration object
    rc_config = projectairsim.rc.RCConfig()

    # Load configuration mapping the Xbox input controller channels to Simple
    # Flight channels
    projectairsim_log().info(f'Loading RC config file "{rc_config_file}"')
    is_rc_loaded = False
    try:
        rc_config.load(rc_config_file)
        is_rc_loaded = True
        print("OOB mapping loaded:", rc_config.channel_map_oob)
    except FileNotFoundError:
        projectairsim_log().error(f"Can't load RC config file: {sys.exc_info()[1]}")

    # Main processing loop
    if is_rc_loaded:
        # Create Xbox input controller object with additional support for
        # Simple Flight
        xbox_input_controller_sf = projectairsim.rc.XboxInputControllerSF()

        # Create the Simple Flight RC object which handles mapping the input
        # controller channels to the Simple Flight controller
        simple_flight_rc = projectairsim.rc.SimpleFlightRC(client, robot_name)
        simple_flight_rc.rc_config = rc_config

        projectairsim_log().info("Startup complete. The drone is ready to fly!")
        projectairsim_log().info(
            "To begin flying, first arm the drone by holding the start button "
            "with the throttle in the neutral position for 0.2s."
        )
        projectairsim_log().info(
            "When done flying, disarm the drone by holding the back button "
            "with the throttle in the neutral position for 0.2s."
        )
        try:
            while True:
                # Get input controller channels when they change
                channels = xbox_input_controller_sf.read()

                # Send channels to Simple Flight
                simple_flight_rc.set(channels)

                # Optional: display RC input sent to the flight controller
                # (you can comment this out if it is too spammy)
                print("RC input channels: ", end="")
                with simple_flight_rc._lock:
                    for channel in simple_flight_rc._channels:
                        print(f"{channel:> 8.4f} ", end="")
                print(end="\r")

        except KeyboardInterrupt:
            print()
            projectairsim_log().info("Exiting...")

    # Shutdown sending RC input to Simple Flight so we can disconnect the client gracefully
    if simple_flight_rc is not None:
        simple_flight_rc.stop()

    # Disconnect the client
    client.disconnect()
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Example of using an Xbox game controller as a remote control for the "
            "Project AirSim Simple Flight flight controller, plus keyboard control for a rover."
        )
    )
    parser.add_argument(
        "--address",
        help=("the IP address of the host running Project AirSim"),
        type=str,
        default="127.0.0.1",
    )
    parser.add_argument(
        "--rcconfigfile",
        help=('the RC config file to load, defaults to "xbox_rc_config.jsonc"'),
        type=str,
        default="xbox_rc_config.jsonc",
    )
    parser.add_argument(
        "--sceneconfigfile",
        help=(
            'the Project AirSim scene config file to load, '
            'defaults to "scene_basic_drone.jsonc"'
        ),
        type=str,
        default="scene_basic_drone.jsonc",
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

    # Create Project AirSim client and load the simulation scene
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

    # Run the drone (Xbox) remote control loop
    main(client, "Drone1", args.rcconfigfile)
