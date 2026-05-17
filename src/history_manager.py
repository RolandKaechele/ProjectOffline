# history_manager.py - Per-view undo / redo history for the Project Offline app
#
# Each view (tasks, resources, dependencies, baseline) has its own independent
# snapshot stack.  A snapshot is the full project serialised as MSPDI XML bytes
# so that every restore produces a perfectly consistent project object.
#
# Timeline design
# ---------------
# stacks[view]['snaps'] : [s0, s1, s2, ...]   (s0 = state after file load)
# stacks[view]['idx']   : index of the CURRENT state in the list
#
# undo()  →  idx -= 1, restore snaps[idx]
# redo()  →  idx += 1, restore snaps[idx]
# push()  →  truncate snaps[idx+1:], append new snapshot, idx = len-1
#
# The initial file-load state sits at idx == 0.  You can undo as far back as
# that state but no further (nothing to undo if idx == 0).


class HistoryManager:
    """Per-view undo/redo history using full-project XML snapshots."""

    VIEWS = ('tasks', 'resources', 'dependencies', 'baseline', 'team_planner')

    def __init__(self, logic):
        self._logic = logic
        self._restoring = False
        # Each entry: {'snaps': [bytes, ...], 'idx': int}
        self._stacks = {v: {'snaps': [], 'idx': -1} for v in self.VIEWS}
        # Optional hooks injected by the main window:
        #   _pre_serialize_hook()  – called just before serialisation (e.g. flush split data)
        #   _post_restore_hook()   – called just after a restore (e.g. reload split data)
        self._pre_serialize_hook = None
        self._post_restore_hook  = None

    def set_hooks(self, pre_serialize=None, post_restore=None):
        """Register optional callbacks for split (and similar) data that lives
        outside the MPXJ project object.

        *pre_serialize* is called with no arguments immediately before the XML
        snapshot is taken, allowing the caller to flush in-memory state (e.g.
        _write_splits_to_project) into the MPXJ object so it is captured.

        *post_restore* is called with no arguments immediately after the project
        object has been replaced by a deserialized snapshot, allowing the caller
        to rebuild in-memory state (e.g. _load_splits) from the new object.
        """
        self._pre_serialize_hook = pre_serialize
        self._post_restore_hook  = post_restore

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def push(self, view: str):
        """Snapshot the current project state and push it onto *view*'s stack.

        Truncates any redo history so that new edits invalidate forward states.
        Does nothing while a restore is in progress or when no project is open.
        """
        if self._restoring:
            return
        snap = self._serialize()
        if snap is None:
            return
        st = self._stacks[view]
        # Truncate redo branch
        st['snaps'] = st['snaps'][:st['idx'] + 1]
        st['snaps'].append(snap)
        st['idx'] = len(st['snaps']) - 1

    def push_all(self):
        """Snapshot current state into ALL view stacks (call after file load).

        Resets each stack to a single entry (the loaded state) so that history
        from a previously-opened project never leaks into the new one.
        """
        if self._restoring:
            return
        snap = self._serialize()
        if snap is None:
            # No project open → clear all stacks
            for v in self.VIEWS:
                self._stacks[v] = {'snaps': [], 'idx': -1}
            return
        for v in self.VIEWS:
            self._stacks[v] = {'snaps': [snap], 'idx': 0}

    def undo(self, view: str) -> bool:
        """Restore the previous state in *view*'s stack.

        Returns True if a step was taken, False when already at the initial
        (post-load) state and nothing can be undone.
        """
        st = self._stacks[view]
        if st['idx'] <= 0:
            return False
        st['idx'] -= 1
        self._restoring = True
        try:
            self._restore(st['snaps'][st['idx']])
        finally:
            self._restoring = False
        return True

    def redo(self, view: str) -> bool:
        """Restore the next state in *view*'s stack.

        Returns True if a step was taken, False when already at the most
        recent state and nothing can be redone.
        """
        st = self._stacks[view]
        if st['idx'] >= len(st['snaps']) - 1:
            return False
        st['idx'] += 1
        self._restoring = True
        try:
            self._restore(st['snaps'][st['idx']])
        finally:
            self._restoring = False
        return True

    def can_undo(self, view: str) -> bool:
        """Return True if there is at least one undo step available."""
        return self._stacks[view]['idx'] > 0

    def can_redo(self, view: str) -> bool:
        """Return True if there is at least one redo step available."""
        st = self._stacks[view]
        return st['idx'] < len(st['snaps']) - 1

    def depth(self, view: str) -> tuple:
        """Return (undo_steps, redo_steps) for *view* — useful for debugging."""
        st = self._stacks[view]
        return st['idx'], len(st['snaps']) - 1 - st['idx']

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _serialize(self) -> bytes | None:
        """Serialise the current project to MSPDI XML bytes.

        Returns None when no project is loaded or serialisation fails.
        Calls the pre_serialize hook first so in-memory state (e.g. splits)
        is flushed into the MPXJ object before writing.
        """
        project = self._logic.get_data()
        if project is None:
            return None
        # Flush any in-memory state that is not yet in the MPXJ object
        if self._pre_serialize_hook is not None:
            try:
                self._pre_serialize_hook()
            except Exception as exc:
                print(f'[HistoryManager] pre_serialize_hook error: {exc}')
        try:
            from org.mpxj.mspdi import MSPDIWriter  # type: ignore
            import jpype  # type: ignore
            ByteArrayOutputStream = jpype.JClass('java.io.ByteArrayOutputStream')
            baos = ByteArrayOutputStream()
            MSPDIWriter().write(project, baos)
            return bytes(baos.toByteArray())
        except Exception as exc:
            print(f'[HistoryManager] serialize error: {exc}')
            return None

    def _restore(self, data: bytes):
        """Deserialise *data* and replace the current project in logic.
        Calls the post_restore hook afterwards so in-memory state (e.g. splits)
        is rebuilt from the newly loaded project object.
        """
        try:
            import jpype  # type: ignore
            from org.mpxj.reader import UniversalProjectReader  # type: ignore
            ByteArrayInputStream = jpype.JClass('java.io.ByteArrayInputStream')
            bais = ByteArrayInputStream(data)
            project = UniversalProjectReader().read(bais)
            self._logic.load_data(project)
        except Exception as exc:
            print(f'[HistoryManager] restore error: {exc}')
            return
        if self._post_restore_hook is not None:
            try:
                self._post_restore_hook()
            except Exception as exc:
                print(f'[HistoryManager] post_restore_hook error: {exc}')
