import asyncio

from projectairsim import ProjectAirSimClient, Rover, Drone, World
from projectairsim.utils import projectairsim_log


async def control_rover(rover: Rover):
    """Minimal rover motion pattern"""
    projectairsim_log().info("Rover: enabling API & arming")
    rover.enable_api_control()
    rover.arm()

    # Move forward
    task = await rover.set_rover_controls(engine=0.4, steering_angle=0.0, brake=0.0)
    await task
    await asyncio.sleep(3)

    # Brake to stop
    task = await rover.set_rover_controls(engine=0.0, steering_angle=0.0, brake=1.0)
    await task
    await asyncio.sleep(1)

    projectairsim_log().info("Rover: shutting down")
    rover.disarm()
    rover.disable_api_control()


async def control_drone(drone: Drone):
    """Minimal drone flight pattern"""
    projectairsim_log().info("Drone: enabling API & arming")
    drone.enable_api_control()
    drone.arm()

    # Takeoff
    projectairsim_log().info("Drone: takeoff")
    takeoff_task = await drone.takeoff_async()
    await takeoff_task

    # Move up
    move_task = await drone.move_by_velocity_async(0, 0, -1.0, 3.0)
    await move_task

    # Land
    projectairsim_log().info("Drone: landing")
    land_task = await drone.land_async()
    await land_task

    drone.disarm()
    drone.disable_api_control()


async def main():
    client = ProjectAirSimClient()

    try:
        client.connect()

        # IMPORTANT:
        # Create a scene that contains BOTH a rover and a drone.
        # Example: "scene_car_and_drone.jsonc"
        world = World(client, "scene_basic_drone_rover.jsonc", delay_after_load_sec=2)

        # Spawn Rover and Drone by their names in the scene JSON
        rover = Rover(client, world, "Rover1")
        drone = Drone(client, world, "Drone1")

        # Run both asynchronously
        await asyncio.gather(
            control_rover(rover),
            control_drone(drone),
        )

    except Exception as err:
        projectairsim_log().error(f"Exception occurred: {err}", exc_info=True)

    finally:
        client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
