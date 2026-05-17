# import_plantuml.py

Parses a PlantUML `@startgantt` file and converts it into an MPXJ `ProjectFile` object that the application can display and save.

## Public API

### `import_plantuml(file_path: str) → ProjectFile`

Parses `file_path` and returns a populated MPXJ `ProjectFile`.

**Raises** an exception if:

- The JVM is not running.
- The file cannot be opened or read.
- The file contains no recognisable task lines.

## Supported PlantUML Syntax

The parser handles the subset of `@startgantt` syntax that `export_gantt.py` produces:

| Line pattern | Meaning |
| - | - |
| `Project starts YYYY-MM-DD` | Project start date |
| `[Display Name] as [Alias] starts YYYY-MM-DD and lasts N days` | Regular task |
| `[Display Name] as [Alias] happens at YYYY-MM-DD` | Milestone (0-day duration) |
| `[Alias] is N% completed` | Sets `% complete` on a previously declared task |
| `[Alias] is colored in …` | Ignored on import |
| `[AliasA] starts after [AliasB]'s end` | Finish-to-Start dependency |

Lines beginning with `'`, `@`, or `printscale` are skipped, as are blank lines.

## How Tasks Are Created

1. Each task line is added to `task_entries` with its display name, alias, start date, duration in days, milestone flag, and `% complete`.
2. After all lines are parsed, an MPXJ `ProjectFile` is constructed in memory.
3. Tasks are added in declaration order, with IDs assigned sequentially.
4. `FINISH_START` `Relation` objects are added between tasks for each `starts after … 's end` line found.
5. Milestones are created with a `Duration` of 0 days and the milestone flag set to `true`.

## Regex Patterns

| Constant | Matches |
| - | - |
| `_RE_PROJECT_START` | `Project starts YYYY-MM-DD` |
| `_RE_TASK_DURATION` | `[Name] as [Alias] starts DATE and lasts N days` |
| `_RE_TASK_MILESTONE` | `[Name] as [Alias] happens at DATE` |
| `_RE_PCT_COMPLETE` | `[Alias] is N% completed` |
| `_RE_COLORED` | `[Alias] is colored in …` |
| `_RE_DEPENDENCY` | `[AliasA] starts after [AliasB]'s end` |
