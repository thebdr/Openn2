"""The phase registry + the dependency DAG (plan §3-§4).

One registry holds every Phase. The phase bar renders by `presentation_order` (ascending number);
the engine runs by `topo_order` (Kahn over `requires`). Both GUIs and the CLI consume THIS registry
- there is no second hand-written ordering. `profile()` restricts to a run profile (main vs the
designer validation-only subset); edges pointing outside the profile are ignored.
"""
from __future__ import annotations


class PhaseRegistry:
    def __init__(self):
        self._by_number: dict = {}
        self._profiles: dict = {}     # name -> RUNNABLE keep-set (phase numbers)
        self._present: dict = {}      # name -> phase numbers SHOWN in the bar (defaults to the keep-set)
        self._attrs: dict = {}        # name -> per-profile GUI behaviour flags (input_pickers, live_source…)

    # --- registration --------------------------------------------------- #
    def register(self, phase):
        if phase.number in self._by_number:
            raise ValueError(f"phase number {phase.number} already registered "
                             f"({self._by_number[phase.number].key})")
        self._by_number[phase.number] = phase
        return phase

    def define_profile(self, name: str, numbers, *, present=None, attrs=None) -> None:
        """`numbers` = the RUNNABLE keep-set (what topo_order may run). `present` = the subset SHOWN in
        the phase bar (default = the keep-set); a number that is runnable-but-not-present runs as a
        HIDDEN prerequisite (e.g. designer stages 300 but only shows 100). `attrs` = arbitrary GUI
        behaviour flags read via profile_attr (so new profiles opt into behaviours by data, not code)."""
        self._profiles[name] = set(numbers)
        self._present[name] = set(present) if present is not None else set(numbers)
        self._attrs[name] = dict(attrs or {})

    def has_profile(self, name) -> bool:
        """True for 'main' (the implicit all-phases profile) or any defined profile."""
        return name == "main" or name in self._profiles

    def profile_attr(self, profile, key, default=None):
        """A per-profile GUI behaviour flag (e.g. 'input_pickers', 'live_source'); default when unset."""
        return self._attrs.get(profile, {}).get(key, default)

    def get(self, number):
        return self._by_number[number]

    def __contains__(self, number):
        return number in self._by_number

    def __len__(self):
        return len(self._by_number)

    # --- selection ------------------------------------------------------ #
    def phases(self, profile: str | None = None) -> list:
        """Phases in a profile, ascending by number. profile None/'main' = all."""
        nums = sorted(self._by_number)
        if profile in (None, "main"):
            return [self._by_number[n] for n in nums]
        if profile not in self._profiles:
            raise KeyError(f"unknown profile {profile!r}")
        keep = self._profiles[profile]
        return [self._by_number[n] for n in nums if n in keep]

    def presentation_order(self, profile: str | None = None) -> list:
        """Left->right phase-bar order = ascending number, filtered to the profile's PRESENTATION set
        (which may be a subset of the runnable keep-set: a hidden prerequisite runs but isn't shown).
        profile None/'main' = all phases."""
        if profile in (None, "main"):
            return self.phases(None)
        if profile not in self._profiles:
            raise KeyError(f"unknown profile {profile!r}")
        show = self._present.get(profile) or self._profiles[profile]
        return [self._by_number[n] for n in sorted(self._by_number) if n in show]

    def topo_order(self, target: int | None = None, profile: str | None = None) -> list:
        """Dependency order via Kahn's algorithm over `requires`, restricted to the profile.
        Ties broken by ascending number (deterministic). If `target` is given, return only the
        target plus its transitive in-profile prerequisites, still topo-sorted. Raises ValueError
        on a cycle."""
        present = {p.number: p for p in self.phases(profile)}

        # restrict to target + transitive prereqs (within `present`) if a target is requested
        if target is not None:
            if target not in present:
                raise KeyError(f"phase {target} not in profile {profile!r}")
            wanted, stack = set(), [target]
            while stack:
                n = stack.pop()
                if n in wanted:
                    continue
                wanted.add(n)
                for dep in present[n].requires:
                    if dep in present and dep not in wanted:
                        stack.append(dep)
            present = {n: p for n, p in present.items() if n in wanted}

        # in-degree counts only edges whose dependency is present
        deps = {n: [d for d in present[n].requires if d in present] for n in present}
        indeg = {n: len(deps[n]) for n in present}
        order, ready = [], sorted(n for n in present if indeg[n] == 0)
        while ready:
            n = ready.pop(0)
            order.append(present[n])
            for m in present:
                if n in deps[m]:
                    indeg[m] -= 1
                    if indeg[m] == 0:
                        ready.append(m)
                        ready.sort()
        if len(order) != len(present):
            cyc = sorted(n for n in present if indeg[n] > 0)
            raise ValueError(f"dependency cycle among phases {cyc}")
        return order


# --- the process-wide singleton ----------------------------------------- #
_REGISTRY = PhaseRegistry()


def registry() -> PhaseRegistry:
    return _REGISTRY


def register(phase):
    """Module-level helper so a phase module can `register(Phase(...))` at import time."""
    return _REGISTRY.register(phase)
