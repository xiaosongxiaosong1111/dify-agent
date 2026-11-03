export type TaskTypeFilter = 'all' | 'workflow' | 'advanced-chat' | 'agent';

// Project only the summaries already loaded by the workspace; preserve order and identity.
export function filterSavedTasks<T extends {name: string; app_type: string}>(
  tasks: readonly T[], query: string, appType: TaskTypeFilter,
): T[] {
  const name = query.trim().toLowerCase();
  return tasks.filter(task => (appType === 'all' || task.app_type === appType)
    && task.name.toLowerCase().includes(name));
}
