"""
Tests for TaskManager class.
"""
import pytest
import asyncio
import sys
import os
from unittest.mock import patch, MagicMock, AsyncMock

# Add src to path so we can import the modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from lib.coresys.manager_tasks import TaskManager, TaskEvent


class TestTaskEvent:
    """Test cases for TaskEvent class"""
    
    def test_task_event_creation(self):
        """Test TaskEvent creation with all parameters."""
        with patch('time.time', return_value=1234567890):
            event = TaskEvent("test_task", TaskEvent.TASK_STARTED, TaskManager.TASK_ONESHOT, error=None)
        
        assert event.task_id == "test_task"
        assert event.event_type == TaskEvent.TASK_STARTED
        assert event.task_type == TaskManager.TASK_ONESHOT
        assert event.error is None
        assert event.timestamp == 1234567890
    
    def test_task_event_with_error(self):
        """Test TaskEvent creation with error."""
        test_error = Exception("Test error")
        event = TaskEvent("test_task", TaskEvent.TASK_FAILED, TaskManager.TASK_PERIODIC, error=test_error)
        
        assert event.error is test_error
        assert event.event_type == TaskEvent.TASK_FAILED
    
    def test_task_event_constants(self):
        """Test TaskEvent constants are defined correctly."""
        assert TaskEvent.TASK_STARTED == 0
        assert TaskEvent.TASK_STOPPED == 1
        assert TaskEvent.TASK_FAILED == 2
        assert TaskEvent.TASK_COMPLETED == 3


class TestTaskManager:
    """Test cases for TaskManager class"""
    
    def setup_method(self):
        """Set up fresh TaskManager for each test."""
        self.task_manager = TaskManager()
        self.events_received = []
        
        # Add event listener to capture events
        def event_listener(event):
            self.events_received.append(event)
        
        self.task_manager.add_listener(event_listener)
    
    def test_task_manager_initialization(self):
        """Test TaskManager initialization."""
        tm = TaskManager()
        
        assert tm._tasks == {}
        assert tm._task_info == {}
        assert tm._listeners == []
        assert tm._next_task_id == 1
    
    def test_task_manager_constants(self):
        """Test TaskManager constants are defined correctly."""
        assert TaskManager.TASK_ONESHOT == 0
        assert TaskManager.TASK_PERIODIC == 1
    
    @pytest.mark.asyncio
    async def test_create_oneshot_task_success(self):
        """Test creating a successful one-shot task."""
        async def test_coro():
            await asyncio.sleep(0.01)
            return "test_result"
        
        task_id = self.task_manager.create_task(test_coro(), task_id="test_task", description="Test task")
        
        # Wait for task to complete
        await asyncio.sleep(0.02)
        
        # Check task was created and completed
        assert task_id == "test_task"
        assert len(self.events_received) == 2
        
        # Check events
        start_event = self.events_received[0]
        assert start_event.task_id == "test_task"
        assert start_event.event_type == TaskEvent.TASK_STARTED
        assert start_event.task_type == TaskManager.TASK_ONESHOT
        
        complete_event = self.events_received[1]
        assert complete_event.task_id == "test_task"
        assert complete_event.event_type == TaskEvent.TASK_COMPLETED
        assert complete_event.task_type == TaskManager.TASK_ONESHOT
        
        # Task should be cleaned up
        assert "test_task" not in self.task_manager._tasks
        assert "test_task" not in self.task_manager._task_info
    
    @pytest.mark.asyncio
    async def test_create_oneshot_task_auto_id(self):
        """Test creating a one-shot task with auto-generated ID."""
        async def test_coro():
            return "result"
        
        task_id = self.task_manager.create_task(test_coro())
        
        # Should generate auto ID
        assert task_id == "oneshot_1"
        assert self.task_manager._next_task_id == 2
        
        # Wait for completion
        await asyncio.sleep(0.01)
    
    @pytest.mark.asyncio
    async def test_create_oneshot_task_failure(self):
        """Test one-shot task that fails with exception."""
        async def failing_coro():
            await asyncio.sleep(0.01)
            raise ValueError("Test error")
        
        task_id = self.task_manager.create_task(failing_coro(), task_id="failing_task")
        
        # Wait for task to fail
        await asyncio.sleep(0.02)
        
        # Check events
        assert len(self.events_received) == 2
        
        start_event = self.events_received[0]
        assert start_event.event_type == TaskEvent.TASK_STARTED
        
        fail_event = self.events_received[1]
        assert fail_event.event_type == TaskEvent.TASK_FAILED
        assert isinstance(fail_event.error, ValueError)
        assert str(fail_event.error) == "Test error"
        
        # Task should be cleaned up
        assert "failing_task" not in self.task_manager._tasks
    
    @pytest.mark.asyncio
    async def test_create_oneshot_task_cancelled(self):
        """Test one-shot task that gets cancelled."""
        async def long_running_coro():
            await asyncio.sleep(1)  # Long running
            return "result"
        
        task_id = self.task_manager.create_task(long_running_coro(), task_id="cancel_task")
        
        # Let it start
        await asyncio.sleep(0.01)
        
        # Cancel the task
        task = self.task_manager._tasks[task_id]
        task.cancel()
        
        # Wait for cancellation to process
        try:
            await task
        except asyncio.CancelledError:
            pass
        
        # Check events
        assert len(self.events_received) == 2
        assert self.events_received[0].event_type == TaskEvent.TASK_STARTED
        assert self.events_received[1].event_type == TaskEvent.TASK_STOPPED
    
    @pytest.mark.asyncio
    async def test_create_periodic_task_sync_function(self):
        """Test creating periodic task with synchronous function."""
        call_count = 0
        
        def sync_update():
            nonlocal call_count
            call_count += 1
        
        task_id = self.task_manager.create_periodic_task(
            sync_update, 
            interval_ms=10, 
            task_id="periodic_sync",
            description="Sync periodic task"
        )
        
        # Let it run for a bit
        await asyncio.sleep(0.05)
        
        # Stop the task
        self.task_manager.stop_task(task_id)
        await asyncio.sleep(0.01)  # Let stop process
        
        # Check it was called multiple times
        assert call_count >= 2
        
        # Check events
        start_events = [e for e in self.events_received if e.event_type == TaskEvent.TASK_STARTED]
        stop_events = [e for e in self.events_received if e.event_type == TaskEvent.TASK_STOPPED]
        
        assert len(start_events) == 1
        assert len(stop_events) == 1
        assert start_events[0].task_type == TaskManager.TASK_PERIODIC
    
    @pytest.mark.asyncio
    async def test_create_periodic_task_async_function(self):
        """Test creating periodic task with asynchronous function."""
        call_count = 0
        
        async def async_update():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.001)  # Small async operation
        
        task_id = self.task_manager.create_periodic_task(
            async_update, 
            interval_ms=10, 
            task_id="periodic_async",
            is_coroutine=True  # Explicitly specify it's async
        )
        
        # Let it run
        await asyncio.sleep(0.05)
        
        # Stop the task
        self.task_manager.stop_task(task_id)
        await asyncio.sleep(0.01)
        
        # Check it was called
        assert call_count >= 2
    
    @pytest.mark.asyncio
    async def test_create_periodic_task_auto_id(self):
        """Test creating periodic task with auto-generated ID."""
        def dummy_update():
            pass
        
        task_id = self.task_manager.create_periodic_task(dummy_update, interval_ms=100)
        
        assert task_id == "periodic_1"
        assert self.task_manager._next_task_id == 2
        
        # Clean up
        self.task_manager.stop_task(task_id)
        await asyncio.sleep(0.01)
    
    @pytest.mark.asyncio
    async def test_periodic_task_update_function_failure(self):
        """Test periodic task when update function fails."""
        call_count = 0
        
        def failing_update():
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("Update failed")
        
        task_id = self.task_manager.create_periodic_task(failing_update, interval_ms=10)
        
        # Let it run and fail
        await asyncio.sleep(0.05)
        
        # Stop the task
        self.task_manager.stop_task(task_id)
        await asyncio.sleep(0.01)
        
        # Should have failure events
        fail_events = [e for e in self.events_received if e.event_type == TaskEvent.TASK_FAILED]
        assert len(fail_events) >= 1
        assert isinstance(fail_events[0].error, RuntimeError)
        
        # Task should still be running despite update failures
        assert call_count > 2  # Should continue after failure
    
    @pytest.mark.asyncio
    async def test_ensure_periodic_task_new(self):
        """Test ensure_periodic_task creates new task when it doesn't exist."""
        def dummy_update():
            pass
        
        task_id = self.task_manager.ensure_periodic_task(
            "ensure_test", 
            dummy_update, 
            interval_ms=100,
            description="Ensured task"
        )
        
        assert task_id == "ensure_test"
        assert self.task_manager.is_task_running("ensure_test")
        
        # Clean up
        self.task_manager.stop_task(task_id)
        await asyncio.sleep(0.01)
    
    @pytest.mark.asyncio
    async def test_ensure_periodic_task_existing(self):
        """Test ensure_periodic_task returns existing task when it exists."""
        def dummy_update():
            pass
        
        # Create initial task
        task_id1 = self.task_manager.create_periodic_task(dummy_update, task_id="ensure_existing")
        
        # Ensure same task
        task_id2 = self.task_manager.ensure_periodic_task("ensure_existing", dummy_update)
        
        assert task_id1 == task_id2 == "ensure_existing"
        
        # Should only have one start event
        start_events = [e for e in self.events_received if e.event_type == TaskEvent.TASK_STARTED]
        assert len(start_events) == 1
        
        # Clean up
        self.task_manager.stop_task(task_id1)
        await asyncio.sleep(0.01)
    
    def test_stop_task_existing(self):
        """Test stopping an existing task."""
        def dummy_update():
            pass
        
        task_id = self.task_manager.create_periodic_task(dummy_update, task_id="stop_test")
        
        # Task should be running
        assert self.task_manager.is_task_running(task_id)
        
        # Stop the task
        result = self.task_manager.stop_task(task_id)
        
        assert result is True
        assert not self.task_manager.is_task_running(task_id)
    
    def test_stop_task_nonexistent(self):
        """Test stopping a non-existent task."""
        result = self.task_manager.stop_task("nonexistent")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_restart_task_existing(self):
        """Test restarting an existing task."""
        call_count = 0
        
        def counting_update():
            nonlocal call_count
            call_count += 1
        
        task_id = self.task_manager.create_periodic_task(counting_update, interval_ms=10, task_id="restart_test")
        
        # Let it run
        await asyncio.sleep(0.03)
        first_count = call_count
        
        # Restart the task
        result = self.task_manager.restart_task(task_id)
        assert result is True
        
        # Let it run again
        await asyncio.sleep(0.03)
        
        # Should have more calls
        assert call_count > first_count
        
        # Clean up
        self.task_manager.stop_task(task_id)
        await asyncio.sleep(0.01)
    
    def test_restart_task_nonexistent(self):
        """Test restarting a non-existent task."""
        result = self.task_manager.restart_task("nonexistent")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_cancel_all_tasks(self):
        """Test cancelling all tasks."""
        def dummy_update():
            pass
        
        # Create multiple tasks
        task1 = self.task_manager.create_periodic_task(dummy_update, task_id="task1")
        task2 = self.task_manager.create_periodic_task(dummy_update, task_id="task2")
        
        assert len(self.task_manager._tasks) == 2
        
        # Cancel all tasks
        self.task_manager.cancel_all_tasks()
        
        # Wait for cancellation to process
        await asyncio.sleep(0.01)
        
        # All tasks should be cancelled
        assert len(self.task_manager._tasks) == 0
    
    def test_is_task_running(self):
        """Test checking if task is running."""
        def dummy_update():
            pass
        
        # Non-existent task
        assert not self.task_manager.is_task_running("nonexistent")
        
        # Create task
        task_id = self.task_manager.create_periodic_task(dummy_update, task_id="running_test")
        assert self.task_manager.is_task_running(task_id)
        
        # Stop task
        self.task_manager.stop_task(task_id)
        assert not self.task_manager.is_task_running(task_id)
    
    def test_get_task_info(self):
        """Test getting task information."""
        def dummy_update():
            pass
        
        # Non-existent task
        assert self.task_manager.get_task_info("nonexistent") is None
        
        # Create task
        with patch('time.time', return_value=1234567890):
            task_id = self.task_manager.create_periodic_task(
                dummy_update, 
                task_id="info_test",
                description="Test task info"
            )
        
        info = self.task_manager.get_task_info(task_id)
        assert info is not None
        assert info['type'] == TaskManager.TASK_PERIODIC
        assert info['description'] == "Test task info"
        assert info['start_time'] == 1234567890
        assert info['running'] is True
        
        # Clean up
        self.task_manager.stop_task(task_id)
    
    def test_get_all_tasks(self):
        """Test getting all task information."""
        def dummy_update():
            pass
        
        # No tasks initially
        all_tasks = self.task_manager.get_all_tasks()
        assert all_tasks == {}
        
        # Create tasks
        task1 = self.task_manager.create_periodic_task(dummy_update, task_id="task1", description="First task")
        task2 = self.task_manager.create_periodic_task(dummy_update, task_id="task2", description="Second task")
        
        all_tasks = self.task_manager.get_all_tasks()
        assert len(all_tasks) == 2
        assert "task1" in all_tasks
        assert "task2" in all_tasks
        assert all_tasks["task1"]['description'] == "First task"
        assert all_tasks["task2"]['description'] == "Second task"
        
        # Clean up
        self.task_manager.cancel_all_tasks()
    
    def test_add_remove_listener(self):
        """Test adding and removing event listeners."""
        events_captured = []
        
        def test_listener(event):
            events_captured.append(event)
        
        # Add listener
        self.task_manager.add_listener(test_listener)
        
        # Create a task to generate events
        def dummy_update():
            pass
        
        task_id = self.task_manager.create_periodic_task(dummy_update, task_id="listener_test")
        
        # Should have received start event
        assert len(events_captured) >= 1
        assert events_captured[0].event_type == TaskEvent.TASK_STARTED
        
        # Remove listener
        self.task_manager.remove_listener(test_listener)
        
        # Stop task (should not generate events for removed listener)
        events_before_stop = len(events_captured)
        self.task_manager.stop_task(task_id)
        
        # Should not have received stop event
        assert len(events_captured) == events_before_stop
    
    def test_remove_nonexistent_listener(self):
        """Test removing a listener that doesn't exist."""
        def dummy_listener(event):
            pass
        
        # Should not raise error
        self.task_manager.remove_listener(dummy_listener)
    
    @pytest.mark.asyncio
    async def test_coroutine_detection(self):
        """Test automatic coroutine detection."""
        call_count = 0
        
        # Regular function
        def sync_func():
            nonlocal call_count
            call_count += 1
        
        # Async function
        async def async_func():
            nonlocal call_count
            call_count += 10
        
        # Test with sync function (auto-detection)
        task1 = self.task_manager.create_periodic_task(sync_func, interval_ms=10, task_id="auto_sync")
        await asyncio.sleep(0.03)
        
        # Test with async function (auto-detection)
        task2 = self.task_manager.create_periodic_task(async_func, interval_ms=10, task_id="auto_async")
        await asyncio.sleep(0.03)
        
        # Both should have been called
        assert call_count >= 12  # At least 2 sync calls (1 each) + 1 async call (10)
        
        # Clean up
        self.task_manager.stop_task(task1)
        self.task_manager.stop_task(task2)
        await asyncio.sleep(0.01)


class TestTaskManagerIntegration:
    """Integration tests for TaskManager functionality."""
    
    @pytest.mark.asyncio
    async def test_complex_task_workflow(self):
        """Test complex workflow with multiple task types and events."""
        task_manager = TaskManager()
        events = []
        
        def event_listener(event):
            events.append(event)
        
        task_manager.add_listener(event_listener)
        
        # Create one-shot task
        async def oneshot_work():
            await asyncio.sleep(0.01)
            return "oneshot_done"
        
        oneshot_id = task_manager.create_task(oneshot_work(), task_id="oneshot")
        
        # Create periodic task
        periodic_calls = 0
        def periodic_work():
            nonlocal periodic_calls
            periodic_calls += 1
        
        periodic_id = task_manager.create_periodic_task(periodic_work, interval_ms=5, task_id="periodic")
        
        # Let them run
        await asyncio.sleep(0.05)
        
        # Stop periodic task
        task_manager.stop_task(periodic_id)
        await asyncio.sleep(0.01)
        
        # Check results
        assert periodic_calls >= 5  # Should have been called multiple times
        
        # Check events
        start_events = [e for e in events if e.event_type == TaskEvent.TASK_STARTED]
        complete_events = [e for e in events if e.event_type == TaskEvent.TASK_COMPLETED]
        stop_events = [e for e in events if e.event_type == TaskEvent.TASK_STOPPED]
        
        assert len(start_events) == 2  # Both tasks started
        assert len(complete_events) == 1  # One-shot completed
        assert len(stop_events) == 1  # Periodic stopped
        
        # One-shot should be cleaned up, periodic should be stopped
        assert not task_manager.is_task_running("oneshot")
        assert not task_manager.is_task_running("periodic")
    
    @pytest.mark.asyncio
    async def test_task_manager_stress_test(self):
        """Stress test with many tasks."""
        task_manager = TaskManager()
        
        # Create many periodic tasks
        task_ids = []
        for i in range(10):
            def make_update(index):
                def update():
                    pass
                return update
            
            task_id = task_manager.create_periodic_task(
                make_update(i), 
                interval_ms=20, 
                task_id=f"stress_{i}"
            )
            task_ids.append(task_id)
        
        # Let them run
        await asyncio.sleep(0.1)
        
        # All should be running
        for task_id in task_ids:
            assert task_manager.is_task_running(task_id)
        
        # Cancel all at once
        task_manager.cancel_all_tasks()
        await asyncio.sleep(0.01)
        
        # All should be stopped
        for task_id in task_ids:
            assert not task_manager.is_task_running(task_id)
        
        assert len(task_manager._tasks) == 0 