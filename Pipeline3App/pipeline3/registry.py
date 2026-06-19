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
        self._profiles: dict = {}     # name -> set of phase numbers

    # --- registration --------------------------------------------------- #
    def register(self, phase):
        if phase.number in self._by_number:
            raise ValueError(f"phase number {phase.number} already registered "
                             f"({self._by_number[phase.number].key})")
        self._by_number[phase.number] = phase
        return phase

    def define_profile(self, name: str, numbers) -> None:
        self._profiles[name] = set(numbers)

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
        """Left->right phase-bar order = ascending number."""
        return self.phases(profile)

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
