"""Static write-set of a loop stage, and the pathspecs that commit it.

    python loop/tools/write_set.py                 # every stage, as a table
    python loop/tools/write_set.py weekly-score    # one stage, in detail

WHY. bin/loop-stage.sh commits a stage's output with NARROW pathspecs, on
purpose. A stage that writes a TRACKED file no pathspec names loses the work
one of two ways, and neither says what happened: `git pull --rebase` refuses
on the dirty file and the job dies "could not push" (run 34687628665, a full
weekly scoring pass thrown away), or nothing else was staged and the script
prints "no repo changes to commit" under a green tick. #79 added a runtime
guard that names the stray file. This module is the STATIC half: it reads the
stage's source and answers "which tracked paths can this stage write, and does
a pathspec cover each one?" BEFORE the stage runs, so the next outgrown
pathspec is a failing test on the PR rather than a red Saturday.

HOW. For each `bin/loop-stage.sh <stage> <entry.py>` in the workflows:

  1. the module closure -- `import x` / `from x import` resolved against
     loop/ and research/, plus every `*.py` a module names as a string (the
     subprocess entrypoints: research/publish_order_domain.py and friends,
     and the research/imagery*.py glob the footage lane runs);
  2. every module-level path constant, evaluated by a small interpreter that
     knows Path(__file__), .parent, os.path.join/dirname/abspath, `/`, str(),
     and f-strings (a dynamic segment becomes `*`);
  3. every write: open(x, "w"/"a"/"x"), x.write_text/write_bytes,
     shutil.copy*/move(src, dst), os.replace/rename(src, dst),
     Path.replace/rename, json.dump into an open(...), AND every call to a
     function in the closure that itself writes to one of its parameters
     (write_json, held._write, ...), found by iterating to a fixpoint;
  4. each write target resolved in its function's context (module constants,
     local assignments, and -- through the fixpoint -- the caller's argument);
  5. only writes REACHABLE from the entry's top-level code count. The import
     graph is deliberately wide here (measure -> breaker -> validate -> every
     lane, so the validators can run), and an import-closure write-set would
     charge every lane with the footage harvest. Reachability follows calls,
     references to functions (callbacks), class construction (__init__),
     `with` (__enter__/__exit__), module aliases, and subprocess entrypoints.
     Where a method name is not unique across the closure every definition
     is taken reachable -- conservative, never silent.

The result is a set of glob patterns relative to the repo root, plus a count
of targets the interpreter could not resolve (reported, never hidden).
"""
from __future__ import annotations

import ast
import fnmatch
import glob as globmod
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(LOOP, ".."))
WORKFLOWS = os.path.join(ROOT, ".github", "workflows")
LOOP_STAGE = os.path.join(ROOT, "bin", "loop-stage.sh")
MODULE_DIRS = (LOOP, os.path.join(ROOT, "research"))

WRITE_MODES = ("w", "a", "x")


# ------------------------------------------------------------------ stages

def stages(workflow_dir: str | None = None) -> list[tuple[str, str, str]]:
    """(stage, entry.py, workflow file) for every loop-stage.sh invocation."""
    out = []
    for path in sorted(globmod.glob(os.path.join(workflow_dir or WORKFLOWS, "*.yml"))):
        text = open(path, encoding="utf-8").read()
        for m in re.finditer(r"bin/loop-stage\.sh\s+([\w-]+)\s+(\S+\.py)", text):
            out.append((m.group(1), m.group(2), os.path.basename(path)))
    return out


def pathspecs(script_text: str | None = None) -> dict[str | None, list[str]]:
    """`git add` pathspecs in loop-stage.sh, keyed by the stage they apply to.

    None is the key for unconditional adds. Reads the script's own structure:
    a `git add` inside `if [ "$STAGE" = "x" ]` (one line or a block) belongs
    to x. Every other `git add` applies to every stage.
    """
    text = script_text if script_text is not None else open(LOOP_STAGE).read()
    out: dict[str | None, list[str]] = {None: []}
    cond: str | None = None
    depth = 0
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r'if \[ "\$STAGE" = "([\w-]+)" \]; then(.*)$', s)
        if m:
            cond, depth = m.group(1), 1
            rest = m.group(2)
            for spec in re.findall(r"git add (?:-- )?(.+?)(?=\s+\d*>|;|&&|\|\||$)", rest):
                out.setdefault(cond, []).extend(spec.split())
            if re.search(r"\bfi\b", rest):
                cond, depth = None, 0
            continue
        if cond is not None:
            if re.match(r"^(if|for|while|case)\b", s):
                depth += 1
            if s == "fi" or s.startswith("fi ") or s == "done" or s == "esac":
                depth -= 1
                if depth <= 0:
                    cond, depth = None, 0
                    continue
        m = re.match(r"git add (?:-- )?(.+?)(?=\s+\d*>|;|&&|\|\||$)", s)
        if m:
            out.setdefault(cond, []).extend(m.group(1).split())
    return out


def specs_for(stage: str, table: dict[str | None, list[str]]) -> list[str]:
    return list(table.get(None, [])) + list(table.get(stage, []))


def covered(relpath: str, specs: list[str]) -> bool:
    """git pathspec semantics, the two shapes this script uses: a directory
    prefix (`loop`, `channel/imagery`) or a glob (`research/competition*.json`).
    """
    for spec in specs:
        spec = spec.rstrip("/")
        if relpath == spec or relpath.startswith(spec + "/"):
            return True
        if any(ch in spec for ch in "*?[") and fnmatch.fnmatchcase(relpath, spec):
            return True
    return False


# ------------------------------------------------------- module closure

def _module_path(name: str) -> str | None:
    base = name.split(".")[-1]
    for d in MODULE_DIRS:
        p = os.path.join(d, base + ".py")
        if os.path.exists(p):
            return p
    return None


class Module:
    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        self.rel = os.path.relpath(self.path, ROOT)
        self.src = open(self.path, encoding="utf-8").read()
        self.tree = ast.parse(self.src, self.path)
        self.env: dict[str, "PathVal | None"] = {}
        self.imports: dict[str, str] = {}      # local name -> module base
        self.functions: dict[str, ast.FunctionDef] = {}
        self.methods: dict[str, list[ast.FunctionDef]] = {}
        for node in self.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.functions[node.name] = node
            elif isinstance(node, ast.ClassDef):
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        self.methods.setdefault(sub.name, []).append(sub)
        self.all_functions: list[ast.FunctionDef] = list(self.functions.values()) + [
            fn for fns in self.methods.values() for fn in fns]


def _norm(pattern: str) -> str:
    """os.path.normpath that keeps `*`, and names the repo root `.`."""
    if pattern.startswith("/"):
        return os.path.normpath(pattern)
    out: list[str] = []
    for seg in pattern.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if out and out[-1] != "..":
                out.pop()
            else:
                out.append("..")
            continue
        out.append(re.sub(r"\*{2,}", "*", seg))
    return "/".join(out) or "."


class PathVal:
    """A path the interpreter resolved: `pattern` is repo-relative (or
    absolute when outside the repo), with `*` where a segment was dynamic."""
    __slots__ = ("pattern", "exact")

    def __init__(self, pattern: str, exact: bool = True):
        self.pattern, self.exact = _norm(pattern), exact

    def join(self, other: "PathVal") -> "PathVal":
        if other.pattern.startswith("/"):
            return other
        return PathVal(self.pattern + "/" + other.pattern, self.exact and other.exact)

    def parent(self) -> "PathVal":
        if self.pattern in (".", "/"):
            return PathVal("..", self.exact) if self.pattern == "." else self
        return PathVal(os.path.dirname(self.pattern) or ".", self.exact)

    def __repr__(self) -> str:
        return self.pattern + ("" if self.exact else "  (dynamic)")


SUBPROCESS_CALLS = ("run", "Popen", "check_call", "check_output", "call")


def _py_candidates(value: str) -> list[str]:
    """Repo .py files a string names: a path, a bare module file, or a glob."""
    if not value.endswith(".py"):
        return []
    if "*" in value:
        out = []
        for d in MODULE_DIRS:
            out.extend(globmod.glob(os.path.join(d, os.path.basename(value))))
        return out
    cand = os.path.normpath(os.path.join(ROOT, value))
    if os.path.exists(cand):
        return [cand]
    mp = _module_path(os.path.basename(value)[:-3])
    return [mp] if mp else []


def closure(entry: str) -> dict[str, Module]:
    """Every repo module the entry reaches by import or by naming a .py."""
    seen: dict[str, Module] = {}
    todo = [os.path.join(ROOT, entry)]
    while todo:
        p = os.path.abspath(todo.pop())
        if p in seen or not os.path.exists(p):
            continue
        m = Module(p)
        seen[p] = m
        pending_names: list[tuple[Module, str]] = []
        pending_globs: list[tuple[Module, str]] = []
        for node in ast.walk(m.tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    mp = _module_path(a.name)
                    if mp:
                        m.imports[(a.asname or a.name).split(".")[0]] = os.path.basename(mp)[:-3]
                        todo.append(mp)
            elif isinstance(node, ast.ImportFrom) and node.module:
                mp = _module_path(node.module)
                if mp:
                    todo.append(mp)
                    for a in node.names:
                        m.imports[a.asname or a.name] = os.path.basename(mp)[:-3] + ":" + a.name
            elif isinstance(node, ast.Call) and _callee(node) in SUBPROCESS_CALLS:
                for c in ast.walk(node):
                    if isinstance(c, ast.Constant) and isinstance(c.value, str):
                        todo.extend(_py_candidates(c.value))
                    elif isinstance(c, ast.Name):
                        pending_names.append((m, c.id))
            elif isinstance(node, ast.Call) and _callee(node) in ("glob", "rglob") \
                    and node.args and isinstance(node.args[0], ast.Constant) \
                    and str(node.args[0].value).endswith(".py"):
                for d in MODULE_DIRS:
                    todo.extend(globmod.glob(os.path.join(d, node.args[0].value)))
            elif isinstance(node, ast.Call) and _callee(node) in ("glob", "rglob") \
                    and node.args and isinstance(node.args[0], ast.Name):
                pending_globs.append((m, node.args[0].id))
        # Names used inside subprocess calls or glob() may be module
        # constants holding a .py path or a *.py pattern; resolve them once
        # the module's constants are known.
        ev = Evaluator({m.path: m})
        for mm, name in pending_names:
            if mm is m:
                v = ev.lookup(name, m, {})
                if v is not None and v.pattern.endswith(".py"):
                    todo.extend(_py_candidates(v.pattern))
        for mm, name in pending_globs:
            if mm is m:
                v = ev.lookup(name, m, {})
                if v is not None and v.pattern.endswith(".py"):
                    for d in MODULE_DIRS:
                        todo.extend(globmod.glob(os.path.join(d, v.pattern)))
        # That evaluator saw ONE module, so constants imported from another
        # did not resolve. Throw its env away; the full evaluator rebuilds it
        # with every module present.
        m.env = {}
    return seen


# ------------------------------------------------------------ evaluator

class Evaluator:
    def __init__(self, mods: dict[str, Module]):
        self.mods = mods
        self.by_base = {os.path.basename(m.path)[:-3]: m for m in mods.values()}
        self._evaluating: set[int] = set()
        for m in mods.values():
            self._module_env(m)

    # -- module constants ---------------------------------------------------
    def _module_env(self, m: Module) -> None:
        if m.env:
            return
        m.env["__file__"] = PathVal(m.rel)
        for node in m.tree.body:
            targets = []
            if isinstance(node, ast.Assign):
                targets, value = node.targets, node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets, value = [node.target], node.value
            else:
                continue
            for t in targets:
                if isinstance(t, ast.Name):
                    val = self.eval(value, m, {})
                    if val is not None:
                        m.env[t.id] = val

    def lookup(self, name: str, m: Module, local: dict) -> PathVal | None:
        if name in local:
            return local[name]
        if name in m.env:
            return m.env[name]
        imp = m.imports.get(name)
        if imp and ":" in imp:
            base, attr = imp.split(":", 1)
            other = self.by_base.get(base)
            if other:
                self._module_env(other)
                return other.env.get(attr)
        return None

    # -- expressions ----------------------------------------------------------
    def eval(self, node, m: Module, local: dict) -> PathVal | None:      # noqa: C901
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return PathVal(node.value)
        if isinstance(node, ast.Name):
            return self.lookup(node.id, m, local)
        if isinstance(node, ast.Attribute):
            base = self.eval(node.value, m, local)
            if node.attr == "parent" and base is not None:
                return base.parent()
            if isinstance(node.value, ast.Name) and node.value.id in m.imports \
                    and ":" not in m.imports[node.value.id]:
                other = self.by_base.get(m.imports[node.value.id])
                if other:
                    self._module_env(other)
                    return other.env.get(node.attr)
            return None
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            a, b = self.eval(node.left, m, local), self.eval(node.right, m, local)
            return a.join(b) if a is not None and b is not None else None
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            a, b = self.eval(node.left, m, local), self.eval(node.right, m, local)
            if a is not None and b is not None:
                return PathVal(a.pattern + b.pattern, a.exact and b.exact)
            return None
        if isinstance(node, ast.JoinedStr):
            parts, exact = [], True
            for v in node.values:
                if isinstance(v, ast.Constant):
                    parts.append(str(v.value))
                else:
                    inner = self.eval(v.value, m, local) if isinstance(v, ast.FormattedValue) else None
                    if inner is not None:
                        parts.append(inner.pattern)
                        exact = exact and inner.exact
                    else:
                        parts.append("*")
                        exact = False
            return PathVal("".join(parts), exact)
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            # `os.environ.get("X") or DEFAULT`: the default is the repo path
            for v in reversed(node.values):
                r = self.eval(v, m, local)
                if r is not None:
                    return r
            return None
        if isinstance(node, ast.Call):
            f = node.func
            fname = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            args = node.args
            target = None
            if isinstance(f, ast.Name):
                if f.id in m.functions:
                    target, tm = m.functions[f.id], m
                else:
                    imp = m.imports.get(f.id)
                    if imp and ":" in imp:
                        base, attr = imp.split(":", 1)
                        other = self.by_base.get(base)
                        if other and attr in other.functions:
                            target, tm = other.functions[attr], other
            elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) \
                    and f.value.id in m.imports and ":" not in m.imports[f.value.id]:
                other = self.by_base.get(m.imports[f.value.id])
                if other and f.attr in other.functions:
                    target, tm = other.functions[f.attr], other
            if target is not None and id(target) not in self._evaluating:
                # A helper in the closure: evaluate what it returns, with its
                # parameters bound to the evaluated arguments (or `*` when an
                # argument is not a path -- `out_path(a.domain)` becomes
                # research/publish_order_*.json). Guarded against recursion.
                self._evaluating.add(id(target))
                try:
                    self._module_env(tm)
                    seed = {}
                    for pname, a in zip(_param_names(target), args):
                        v = self.eval(a, m, local)
                        seed[pname] = v if v is not None else PathVal("*", False)
                    for pname in _param_names(target)[len(args):]:
                        seed.setdefault(pname, PathVal("*", False))
                    for kw in node.keywords:
                        if kw.arg:
                            v = self.eval(kw.value, m, local)
                            seed[kw.arg] = v if v is not None else PathVal("*", False)
                    inner = _local_env(target, self, tm, seed)
                    for n in ast.walk(target):
                        if isinstance(n, ast.Return) and n.value is not None:
                            r = self.eval(n.value, tm, inner)
                            if r is not None:
                                return r
                finally:
                    self._evaluating.discard(id(target))
                return None
            if fname in ("Path", "PurePath", "abspath", "realpath", "resolve",
                         "absolute", "str", "expanduser", "fspath"):
                if fname in ("resolve", "absolute", "expanduser") and isinstance(f, ast.Attribute):
                    return self.eval(f.value, m, local)
                return self.eval(args[0], m, local) if args else None
            if fname == "dirname" and args:
                v = self.eval(args[0], m, local)
                return v.parent() if v is not None else None
            if fname == "join" and isinstance(f, ast.Attribute) and args:
                acc = self.eval(args[0], m, local)
                for a in args[1:]:
                    nxt = self.eval(a, m, local)
                    if acc is None or nxt is None:
                        return None
                    acc = acc.join(nxt)
                return acc
            if fname in ("with_suffix", "with_name") and isinstance(f, ast.Attribute):
                base = self.eval(f.value, m, local)
                if base is None:
                    return None
                if fname == "with_name" and args:
                    n = self.eval(args[0], m, local)
                    return base.parent().join(n) if n is not None else None
                suf = self.eval(args[0], m, local) if args else None
                if suf is None:
                    return None
                stem = re.sub(r"\.[^./]*$", "", base.pattern)
                return PathVal(stem + suf.pattern, base.exact and suf.exact)
            if fname == "get" and isinstance(f, ast.Attribute) and len(node.args) > 1:
                # `os.environ.get("X", default)` and `TABLE.get(key, default)`:
                # the default is the path this repo computes; an override is a
                # sibling of it. Marked dynamic so a glob pathspec is expected.
                d = self.eval(node.args[1], m, local)
                return PathVal(d.pattern, False) if d is not None else None
            return None
        return None


# --------------------------------------------------------------- writes

def _mode_is_write(call: ast.Call) -> bool:
    mode = None
    if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant):
        mode = call.args[1].value
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            mode = kw.value.value
    return isinstance(mode, str) and mode[:1] in WRITE_MODES


def _callee(call: ast.Call) -> str | None:
    f = call.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return None


def _write_targets(call: ast.Call, m: Module, by_base: dict[str, Module],
                   writers: dict[int, set[int]]) -> list[ast.AST]:
    """Expressions this call writes to, if any."""
    name = _callee(call)
    f = call.func
    if name == "open" and _mode_is_write(call) and call.args:
        return [call.args[0]]
    if name in ("write_text", "write_bytes") and isinstance(f, ast.Attribute):
        return [f.value]
    if name in ("copy", "copy2", "copyfile", "move") and isinstance(f, ast.Attribute) \
            and isinstance(f.value, ast.Name) and f.value.id == "shutil" and len(call.args) >= 2:
        return [call.args[1]]
    if name in ("replace", "rename"):
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "os" \
                and len(call.args) >= 2:
            return [call.args[1]]
        if isinstance(f, ast.Attribute) and call.args and not (
                isinstance(f.value, ast.Constant)):
            # Path.replace(target) / Path.rename(target); str.replace is
            # excluded by requiring a single positional (str.replace has two)
            if len(call.args) == 1:
                return [call.args[0]]
    if name in SUBPROCESS_CALLS and call.args:
        # A subprocess entrypoint from this repo: every argv element that is
        # not the interpreter or the script is a possible OUTPUT path (the
        # entrypoint's own argparse `--out` is opaque from here, so it is
        # attributed at the call site). Counting an input path as a write is
        # the safe direction; a covered path costs nothing.
        argv = call.args[0]
        elts = None
        if isinstance(argv, (ast.List, ast.Tuple)):
            elts = argv.elts
        elif isinstance(argv, ast.Name):
            # `cmd = [...]; subprocess.run(cmd)`: the list it was built from
            fn = _enclosing.get(id(call))
            for n in (ast.walk(fn) if fn is not None else ()):
                if isinstance(n, ast.Assign) and len(n.targets) == 1 \
                        and isinstance(n.targets[0], ast.Name) \
                        and n.targets[0].id == argv.id \
                        and isinstance(n.value, (ast.List, ast.Tuple)):
                    elts = n.value.elts
        if elts and any(isinstance(c, ast.Constant) and isinstance(c.value, str)
                        and _py_candidates(c.value)
                        for e in elts for c in ast.walk(e)):
            return [e for e in elts[1:] if _argv_pathlike(e)]
        return []
    hit = _resolve_callee(call, m, by_base)
    if hit is not None:
        _, fn, is_method = hit
        idxs = writers.get(id(fn), set())
        out = []
        for i in idxs:
            j = i - 1 if is_method else i       # drop `self`
            if 0 <= j < len(call.args):
                out.append(call.args[j])
        return out
    return []


# id(Call) -> innermost enclosing FunctionDef, filled by the walkers below so
# the argv rule can find the list a subprocess command was built from.
_enclosing: dict[int, ast.AST] = {}


def _index_enclosing(mods: dict[str, Module]) -> None:
    for m in mods.values():
        for fn in m.all_functions:
            for n in ast.walk(fn):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n is not fn:
                    continue
                _enclosing.setdefault(id(n), fn)


def _cli_sourced(fn: ast.AST | None, m: "Module | None" = None) -> set[str]:
    """Names whose value comes from argv, argparse or the environment, in the
    function and at module level."""
    out: set[str] = set()
    scopes = [x for x in (fn, m.tree if m is not None else None) if x is not None]
    for scope in scopes:
        for n in ast.walk(scope):
            if isinstance(n, ast.Assign) and len(n.targets) == 1:
                text = ast.unparse(n.value)
                if re.search(r"sys\.argv|environ|parse_args|\bargs\.", text):
                    t = n.targets[0]
                    for nm in ([t] if isinstance(t, ast.Name) else
                               [x for x in getattr(t, "elts", []) if isinstance(x, ast.Name)]):
                        out.add(nm.id)
    return out


def _argv_pathlike(e: ast.AST) -> bool:
    """Could this argv element be a path? Flags, the script, `str(budget)`
    and `",".join(queries)` are not; names, joins and f-strings may be."""
    if isinstance(e, ast.Constant):
        return False
    if isinstance(e, ast.Call):
        name = _callee(e)
        if name == "str":
            return False
        if name == "join" and isinstance(e.func, ast.Attribute) \
                and isinstance(e.func.value, ast.Constant):
            return False
    return True


def _invokes_repo_entrypoint(call: ast.Call, m: Module) -> bool:
    """Does this subprocess call name a .py that lives in this repo?"""
    for c in ast.walk(call):
        if isinstance(c, ast.Constant) and isinstance(c.value, str) \
                and _py_candidates(c.value):
            return True
    return False


def _param_names(fn: ast.FunctionDef) -> list[str]:
    return [a.arg for a in fn.args.posonlyargs + fn.args.args]


def _provenance(fn: ast.FunctionDef) -> dict[str, set[str]]:
    """local name -> the parameters it derives from (transitively).

    `p = path.with_suffix(".tmp")` gives p -> {path}, so a write to `p` is a
    write to whatever the CALLER passed as `path` -- and only that: the data
    argument beside it is never mistaken for a second target.
    """
    prov: dict[str, set[str]] = {p: {p} for p in _param_names(fn)}
    changed = True
    while changed:
        changed = False
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                    and isinstance(node.targets[0], ast.Name):
                used = {n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)}
                src = set()
                for u in used:
                    src |= prov.get(u, set())
                tgt = node.targets[0].id
                if src and not src <= prov.get(tgt, set()):
                    prov[tgt] = prov.get(tgt, set()) | src
                    changed = True
    return prov


def _param_derived(fn: ast.FunctionDef) -> set[str]:
    """Names that are parameters or derive from one."""
    return set(_provenance(fn))


def _local_env(fn: ast.AST, ev: Evaluator, m: Module, seed: dict) -> dict:
    """Locals assigned from evaluable path expressions, in source order."""
    local = dict(seed)
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            v = ev.eval(node.value, m, local)
            if v is not None:
                local[node.targets[0].id] = v
        elif isinstance(node, ast.AnnAssign) and node.value is not None \
                and isinstance(node.target, ast.Name):
            v = ev.eval(node.value, m, local)
            if v is not None:
                local[node.target.id] = v
    return local


def _resolve_callee(call: ast.Call, m: Module, mods_by_base: dict[str, Module]):
    """(Module, FunctionDef, is_method) the call reaches, or None.

    A bare name resolves in the calling module, then through its imports. An
    attribute call on an imported module alias resolves there. An attribute
    call on anything else resolves to a METHOD of that name if exactly one
    class in the closure defines it -- never to a top-level function, which
    is how research/competition.py's `named_stop(path)` was once mistaken for
    `Stage.named_stop(code)` and every stop code became a "write target".
    """
    f = call.func
    if isinstance(f, ast.Name):
        if f.id in m.functions:
            return m, m.functions[f.id], False
        imp = m.imports.get(f.id)
        if imp and ":" in imp:
            base, attr = imp.split(":", 1)
            other = mods_by_base.get(base)
            if other and attr in other.functions:
                return other, other.functions[attr], False
        return None
    if isinstance(f, ast.Attribute):
        if isinstance(f.value, ast.Name) and f.value.id in m.imports \
                and ":" not in m.imports[f.value.id]:
            other = mods_by_base.get(m.imports[f.value.id])
            if other and f.attr in other.functions:
                return other, other.functions[f.attr], False
            return None
        found = [(mm, fn) for mm in mods_by_base.values()
                 for fn in mm.methods.get(f.attr, [])]
        if len(found) == 1:
            return found[0][0], found[0][1], True
    return None


def writers_fixpoint(mods: dict[str, Module], ev: "Evaluator") -> dict[int, set[int]]:
    """id(FunctionDef) -> positional indexes of parameters it writes to.

    A parameter is credited only when the target does NOT resolve inside the
    function itself. `author.py` writes `DRAFTS / f"{slug}.md"`: that resolves
    locally to loop/drafts/*.md, so `slug` is a name, not a path, and the
    caller's `slug` argument is not a write target.
    """
    by_base = {os.path.basename(mm.path)[:-3]: mm for mm in mods.values()}
    writers: dict[int, set[int]] = {}
    changed = True
    while changed:
        changed = False
        for m in mods.values():
            for fn in m.all_functions:
                params = _param_names(fn)
                local = None
                for call in (n for n in ast.walk(fn) if isinstance(n, ast.Call)):
                    for tgt in _write_targets(call, m, by_base, writers):
                        if local is None:
                            local = _local_env(fn, ev, m, {})
                        if ev.eval(tgt, m, local) is not None:
                            continue
                        names = {n.id for n in ast.walk(tgt) if isinstance(n, ast.Name)}
                        prov = _provenance(fn)
                        origins = set()
                        for n in names:
                            origins |= prov.get(n, set())
                        for i, p in enumerate(params):
                            if p in origins and i not in writers.get(id(fn), set()):
                                writers.setdefault(id(fn), set()).add(i)
                                changed = True
    return writers


def _class_index(mods: dict[str, Module]) -> dict[str, list[ast.ClassDef]]:
    idx: dict[str, list[ast.ClassDef]] = {}
    for m in mods.values():
        for node in m.tree.body:
            if isinstance(node, ast.ClassDef):
                idx.setdefault(node.name, []).append(node)
    return idx


def _fns_of_class(cls: ast.ClassDef, names: tuple[str, ...]) -> list[ast.FunctionDef]:
    return [n for n in cls.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]


def reachable(entry_mods: list[Module], mods: dict[str, Module]) -> set[int]:
    """id() of every FunctionDef the entry module's top-level code can reach."""
    by_base = {os.path.basename(mm.path)[:-3]: mm for mm in mods.values()}
    classes = _class_index(mods)
    owner: dict[int, Module] = {}
    for mm in mods.values():
        for fn in mm.all_functions:
            owner[id(fn)] = mm
    seen: set[int] = set()
    work: list[tuple[Module, ast.AST]] = []

    for em in entry_mods:
        for node in em.tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                work.append((em, node))

    def enqueue(fn: ast.FunctionDef) -> None:
        if id(fn) not in seen:
            seen.add(id(fn))
            work.append((owner[id(fn)], fn))

    def enqueue_class(cls: ast.ClassDef, names: tuple[str, ...]) -> None:
        for fn in _fns_of_class(cls, names):
            enqueue(fn)

    def by_name(m: Module, name: str):
        """Function a bare name refers to in module m, if any."""
        if name in m.functions:
            return m.functions[name]
        imp = m.imports.get(name)
        if imp and ":" in imp:
            base, attr = imp.split(":", 1)
            other = by_base.get(base)
            if other and attr in other.functions:
                return other.functions[attr]
        return None

    def class_by_name(m: Module, name: str) -> list[ast.ClassDef]:
        imp = m.imports.get(name)
        if imp and ":" in imp:
            name = imp.split(":", 1)[1]
        return classes.get(name, [])

    while work:
        m, node = work.pop()
        for n in ast.walk(node):
            if isinstance(n, ast.Name):
                fn = by_name(m, n.id)
                if fn is not None:
                    enqueue(fn)
                for cls in class_by_name(m, n.id):
                    enqueue_class(cls, ("__init__", "__new__", "__post_init__"))
            elif isinstance(n, ast.Attribute):
                if isinstance(n.value, ast.Name) and n.value.id in m.imports \
                        and ":" not in m.imports[n.value.id]:
                    other = by_base.get(m.imports[n.value.id])
                    if other:
                        if n.attr in other.functions:
                            enqueue(other.functions[n.attr])
                        for cls in classes.get(n.attr, []):
                            if any(c is cls for c in other.tree.body):
                                enqueue_class(cls, ("__init__",))
                else:
                    # method on an object we cannot type: every definition of
                    # that name in the closure. Conservative on purpose.
                    for mm in mods.values():
                        for fn in mm.methods.get(n.attr, []):
                            enqueue(fn)
            elif isinstance(n, ast.With):
                for item in n.items:
                    ctx = item.context_expr
                    tgt = ctx.func if isinstance(ctx, ast.Call) else ctx
                    names = []
                    if isinstance(tgt, ast.Name):
                        names = class_by_name(m, tgt.id)
                    elif isinstance(tgt, ast.Attribute):
                        names = classes.get(tgt.attr, [])
                    for cls in names:
                        enqueue_class(cls, ("__enter__", "__exit__", "__init__"))
        # A subprocess entrypoint anywhere in this node makes that file's
        # module-level code a new root. The .py may sit in a list built on an
        # earlier line (`cmd = [sys.executable, os.path.join(HERE,
        # "competition.py")]; subprocess.run(cmd)`), so once a subprocess
        # call is present the WHOLE node is scanned for .py literals and for
        # names that evaluate to a .py path.
        if any(isinstance(c, ast.Call) and _callee(c) in SUBPROCESS_CALLS
               for c in ast.walk(node)):
            ev = Evaluator(mods)
            local = _local_env(node, ev, m, {}) if not isinstance(node, ast.Module) else {}
            for c in ast.walk(node):
                cands: list[str] = []
                if isinstance(c, ast.Constant) and isinstance(c.value, str):
                    cands = _py_candidates(c.value)
                elif isinstance(c, ast.Name):
                    v = ev.lookup(c.id, m, local)
                    if v is not None and v.pattern.endswith(".py"):
                        cands = _py_candidates(v.pattern)
                for cand in cands:
                    mm = mods.get(os.path.abspath(cand))
                    if mm is not None and id(mm.tree) not in seen:
                        seen.add(id(mm.tree))
                        for top in mm.tree.body:
                            if not isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef,
                                                    ast.ClassDef)):
                                work.append((mm, top))
    return seen


def write_set(entry: str) -> tuple[list[PathVal], list[str], dict[str, Module]]:
    """(resolved targets, unresolved descriptions, closure) for one entry."""
    mods = closure(entry)
    ev = Evaluator(mods)
    by_base = {os.path.basename(mm.path)[:-3]: mm for mm in mods.values()}
    _index_enclosing(mods)
    writers = writers_fixpoint(mods, ev)
    entry_mod = mods[os.path.abspath(os.path.join(ROOT, entry))]
    reach = reachable([entry_mod], mods)
    resolved: dict[str, PathVal] = {}
    unresolved: list[str] = []
    cli_sourced: list[str] = []

    for m in mods.values():
        # map each Call to its innermost enclosing function once
        parents: dict[int, ast.AST] = {}
        for fn in m.all_functions:
            for n in ast.walk(fn):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n is not fn:
                    continue
                parents.setdefault(id(n), fn)
        for call in (n for n in ast.walk(m.tree) if isinstance(n, ast.Call)):
            fn = parents.get(id(call))
            # module-level code runs on import; function bodies only if reached
            if fn is not None and id(fn) not in reach:
                continue
            tgts = _write_targets(call, m, by_base, writers)
            if not tgts:
                continue
            local = _local_env(fn, ev, m, {}) if fn is not None else {}
            is_argv = _callee(call) in SUBPROCESS_CALLS
            for tgt in tgts:
                v = ev.eval(tgt, m, local)
                if v is not None and v.pattern.endswith(".py"):
                    continue                    # the script itself, not an output
                if v is None and is_argv:
                    # a non-path argv string (a domain name, a query list) or
                    # a temp file; the fixpoint has already credited any
                    # parameter here to its caller.
                    continue
                if v is None:
                    # the target is a parameter, or a local derived from one:
                    # the fixpoint credits it to the caller, which is resolved
                    # at the caller's call site.
                    names = {n.id for n in ast.walk(tgt) if isinstance(n, ast.Name)}
                    if fn is not None and names & _param_derived(fn):
                        continue
                    text = ast.unparse(tgt)
                    if re.search(r"\bargs?\b|sys\.argv|environ|\bcwd\b", text) \
                            or names & {"args", "a", "ns", "opts"} \
                            or names & _cli_sourced(fn, m):
                        # supplied by argparse / argv / the environment: the
                        # caller names the real path and is resolved there.
                        cli_sourced.append(f"{m.rel}:{call.lineno} {text}")
                    else:
                        unresolved.append(f"{m.rel}:{call.lineno} {text}")
                    continue
                key = v.pattern
                if key not in resolved or (v.exact and not resolved[key].exact):
                    resolved[key] = v
    return (sorted(resolved.values(), key=lambda p: p.pattern),
            unresolved + [f"{u}  [cli/env-sourced; attributed at its caller]"
                          for u in cli_sourced], mods)


# ---------------------------------------------------------------- report

def tracked_files() -> list[str]:
    r = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    return r.stdout.split()


def tracked_matches(pattern: str, tracked: list[str]) -> list[str]:
    if pattern.startswith("/"):
        return []
    pattern = os.path.normpath(pattern) if "*" not in pattern else pattern
    if "*" in pattern:
        return [t for t in tracked if fnmatch.fnmatchcase(t, pattern)]
    return [t for t in tracked if t == pattern or t.startswith(pattern + "/")]


def audit(stage: str, entry: str, table, tracked) -> dict:
    targets, unresolved, mods = write_set(entry)
    specs = specs_for(stage, table)
    stray: dict[str, list[str]] = {}
    hits: dict[str, list[str]] = {}
    for t in targets:
        files = tracked_matches(t.pattern, tracked)
        if not files:
            continue
        hits[t.pattern] = files
        bad = [f for f in files if not covered(f, specs)]
        if bad:
            stray[t.pattern] = bad
    return {"stage": stage, "entry": entry, "modules": sorted(m.rel for m in mods.values()),
            "targets": targets, "tracked_hits": hits, "stray": stray,
            "unresolved": unresolved, "specs": specs}


def main(argv: list[str]) -> int:
    table = pathspecs()
    tracked = tracked_files()
    want = set(argv[1:])
    rc = 0
    for stage, entry, wf in stages():
        if want and stage not in want:
            continue
        a = audit(stage, entry, table, tracked)
        print(f"\n== {stage}  ({entry}, {wf})  specs={a['specs']}")
        print(f"   closure: {len(a['modules'])} module(s)")
        for t in a["targets"]:
            files = a["tracked_hits"].get(t.pattern)
            mark = "  " if not files else ("!!" if t.pattern in a["stray"] else "ok")
            print(f"   {mark} {t!r}" + (f"  -> {len(files)} tracked" if files else ""))
        for u in a["unresolved"]:
            print(f"   ?? unresolved write target: {u}")
        if a["stray"]:
            rc = 1
            for pat, files in a["stray"].items():
                print(f"   STRAY {pat}: {files[:5]}")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
