import uasyncio as asyncio
import time
from lib.manager_system import SystemManager
from lib.manager_tasks import TaskManager, TaskEvent

# Example using TaskManager directly
async def example_with_task_manager():
    print("Starting TaskManager example")
    
    # Create a task manager
    task_manager = TaskManager()
    
    # Create a listener to see task events
    def task_listener(event):
        print(f"Task event: {event.task_id} - " + 
              f"{'STARTED' if event.event_type == TaskEvent.TASK_STARTED else ''}" +
              f"{'STOPPED' if event.event_type == TaskEvent.TASK_STOPPED else ''}" +
              f"{'COMPLETED' if event.event_type == TaskEvent.TASK_COMPLETED else ''}" +
              f"{'FAILED' if event.event_type == TaskEvent.TASK_FAILED else ''}")
        if event.error:
            print(f"  Error: {event.error}")
            
    task_manager.add_listener(task_listener)
    
    # Example of a one-shot coroutine
    async def example_coroutine():
        print("  Example coroutine starting")
        await asyncio.sleep(2)
        print("  Example coroutine finishing")
        return "Done!"
    
    # Example of a periodic function
    counter = 0
    def periodic_function():
        nonlocal counter
        counter += 1
        print(f"  Periodic function called ({counter})")
        if counter >= 5:
            # Intentionally raise an exception to demonstrate error handling
            raise ValueError("Example error in periodic function")
    
    # Create the tasks
    oneshot_id = task_manager.create_task(
        example_coroutine(),
        description="Example one-shot coroutine"
    )
    print(f"Created one-shot task with ID: {oneshot_id}")
    
    periodic_id = task_manager.create_periodic_task(
        periodic_function,
        interval_ms=1000,  # Call every second
        description="Example periodic function",
        is_coroutine=False  # Explicitly specify this is not a coroutine
    )
    print(f"Created periodic task with ID: {periodic_id}")
    
    # Let the tasks run for a while
    await asyncio.sleep(10)
    
    # Stop the periodic task if still running
    if task_manager.is_task_running(periodic_id):
        print(f"Stopping periodic task {periodic_id}")
        task_manager.stop_task(periodic_id)
    
    # Clean up
    task_manager.cancel_all_tasks()
    print("TaskManager example completed")

# Example using SystemManager
async def example_with_system_manager():
    print("\nStarting SystemManager example")
    
    # Initialize the system manager
    system = SystemManager(config_file="/config.json")
    system.init()
    
    # Create a simple async task
    async def system_example_coro():
        print("  System example coroutine running")
        await asyncio.sleep(3)
        print("  System example coroutine completed")
    
    # Create a simple periodic task
    counter = 0
    def system_periodic_func():
        nonlocal counter
        counter += 1
        print(f"  System periodic function called ({counter})")
    
    # Create tasks through the system manager
    system_task_id = system.create_task(
        system_example_coro(),
        description="System example coroutine"
    )
    print(f"Created system task with ID: {system_task_id}")
    
    system_periodic_id = system.create_periodic_task(
        system_periodic_func,
        interval_ms=1000,
        description="System periodic function",
        is_coroutine=False  # Explicitly specify this is not a coroutine
    )
    print(f"Created system periodic task with ID: {system_periodic_id}")
    
    # Let tasks run for a while
    await asyncio.sleep(5)
    
    # Stop the periodic task
    system.stop_task(system_periodic_id)
    print(f"Stopped periodic task: {system_periodic_id}")
    
    # Wait for any remaining tasks
    await asyncio.sleep(2)
    
    # Clean up
    system.cancel_all_tasks()
    print("SystemManager example completed")

async def main():
    # Run examples
    await example_with_task_manager()
    await example_with_system_manager()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Example interrupted")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        print("Example finished") 