import unittest

from schemas.task_dag import TaskDAG, TaskNode


class TaskDAGTests(unittest.TestCase):
    def test_ready_tasks_respect_dependencies(self):
        first = TaskNode(title="Plan", description="Plan work", assigned_to="Planner")
        second = TaskNode(
            title="Build",
            description="Build work",
            assigned_to="Executor",
            depends_on=[first.task_id],
        )
        dag = TaskDAG(goal="Build thing", tasks=[first, second])

        dag.validate()
        self.assertEqual([task.title for task in dag.ready_tasks()], ["Plan"])

        first.status = "done"
        self.assertEqual([task.title for task in dag.ready_tasks()], ["Build"])

    def test_cycle_is_rejected(self):
        first = TaskNode(title="A", description="A", assigned_to="Planner")
        second = TaskNode(title="B", description="B", assigned_to="Executor", depends_on=[first.task_id])
        first.depends_on = [second.task_id]
        dag = TaskDAG(goal="Bad graph", tasks=[first, second])

        with self.assertRaises(ValueError):
            dag.validate()


if __name__ == "__main__":
    unittest.main()

