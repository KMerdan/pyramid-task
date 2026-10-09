"""Bounded advisory dependency extraction. Never execute repository code.

ast-grep supplies syntax ranges; the stdlib fallback recognizes a documented
subset. Neither provider establishes semantic completeness or mutation authority.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from bisect import bisect_right
from pathlib import Path

VERSION = '3'
LANGUAGES = {'.js': 'JS', '.mjs': 'JS', '.cjs': 'JS', '.jsx': 'JSX',
             '.ts': 'TS', '.mts': 'TS', '.cts': 'TS', '.tsx': 'TSX',
             '.rs': 'Rust', '.py': 'Python'}
MAX_FILE_BYTES = 1024 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
CONFIG_NAMES = ('tsconfig.json', 'jsconfig.json', 'package.json', 'package-lock.json',
                'pnpm-lock.yaml', 'yarn.lock', 'Cargo.toml', 'Cargo.lock')
MAX_RUST_MODULE_FILES = 256
MAX_RUST_MODULE_BYTES = 4 * 1024 * 1024
MAX_RUST_MODULE_DEPTH = 32


@dataclass(frozen=True)
class Token:
    value: str
    kind: str
    start: int
    line: int
    column: int


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def safe_file(root: Path, relative: str) -> Path:
    path = root / relative
    if Path(relative).is_absolute() or '..' in Path(relative).parts or not path.resolve().is_relative_to(root):
        raise ValueError('Input is outside the project')
    if path.is_symlink() or not path.is_file():
        raise ValueError('Input must be a regular in-project file')
    return path


def tokenize(text: str, language: str, *, jsx=True):
    """Finite lexer, not a general parser. Keep positions; ignore literal contents."""
    tokens, problems = [], []
    i = 0
    newlines = [-1] + [match.start() for match in re.finditer('\n', text)]
    def add(value, kind, start):
        line = bisect_right(newlines, start - 1)
        column = start - newlines[line - 1]
        tokens.append(Token(value, kind, start, line, column))
    while i < len(text):
        start = i
        if text[i].isspace():
            i += 1; continue
        if jsx and language in {'JSX', 'TSX'} and text[i] == '<' and re.match(r'<[A-Za-z>]', text[i:]):
            # Fallback treats JSX elements as an explicit unsupported expression
            # boundary. Static declarations outside remain usable; markup text
            # must never manufacture import references.
            depth = 0; cursor = i
            while cursor < len(text):
                if text[cursor] == '{': problems.append((cursor, 'jsx-expression-unresolved'))
                if text[cursor] == '<':
                    closing = text.startswith('</', cursor); end = cursor + 1; quote = None
                    while end < len(text):
                        char = text[end]
                        if quote:
                            if char == '\\': end += 2; continue
                            if char == quote: quote = None
                        elif char in "\"'": quote = char
                        elif char == '{': problems.append((end, 'jsx-expression-unresolved'))
                        elif char == '>': break
                        end += 1
                    if end == len(text): problems.append((start, 'unterminated-jsx')); cursor = end; break
                    self_closing = text[end - 1] == '/'
                    depth += -1 if closing else (0 if self_closing else 1)
                    cursor = end + 1
                    if depth <= 0: break
                else: cursor += 1
            i = cursor; continue
        if text.startswith('//', i):
            end = text.find('\n', i); i = len(text) if end < 0 else end; continue
        if text.startswith('/*', i):
            i += 2; depth = 1
            while i < len(text) and depth:
                if language == 'Rust' and text.startswith('/*', i):
                    depth += 1; i += 2
                elif text.startswith('*/', i):
                    depth -= 1; i += 2
                else: i += 1
            if depth: problems.append((start, 'unterminated-comment'))
            continue
        raw = re.match(r'(?:br|r)(\#*)"', text[i:]) if language == 'Rust' else None
        if raw:
            closing = '"' + raw.group(1); begin = i + raw.end(); end = text.find(closing, begin)
            if end < 0:
                problems.append((start, 'unterminated-string')); break
            add(text[begin:end], 'string', start); i = end + len(closing); continue
        if text[i] in "\"'`":
            quote = text[i]
            if language == 'Rust' and quote == "'" and re.match(r"'[A-Za-z_]\w*(?!')", text[i:]):
                # A lifetime has no closing quote; character literals do.
                candidate = re.match(r"'[A-Za-z_]\w*", text[i:]).group()
                if i + len(candidate) >= len(text) or text[i + len(candidate)] != "'":
                    add(candidate, 'lifetime', start); i += len(candidate); continue
            i += 1; content = ''
            while i < len(text) and text[i] != quote:
                if text[i] == '\\' and i + 1 < len(text):
                    escaped = text[i + 1]
                    if escaped in "\\\"'`": content += escaped
                    elif escaped in 'nrt': content += {'n': '\n', 'r': '\r', 't': '\t'}[escaped]
                    else:
                        problems.append((start, 'unsupported-string-escape')); content += '\\' + escaped
                    i += 2
                else: content += text[i]; i += 1
            if i == len(text):
                problems.append((start, 'unterminated-string')); break
            add(content, 'dynamic-string' if quote == '`' and '${' in content else 'string', start)
            i += 1; continue
        # Avoid interpreting import-like contents of common JS regex literals.
        if language != 'Rust' and text[i] == '/' and (not tokens or tokens[-1].value in {'=', '(', '[', ',', ':', 'return', '=>'}):
            i += 1; in_class = False
            while i < len(text) and text[i] != '\n':
                if text[i] == '\\': i += 2; continue
                if text[i] == '[': in_class = True
                if text[i] == ']': in_class = False
                if text[i] == '/' and not in_class:
                    i += 1
                    while i < len(text) and text[i].isalpha(): i += 1
                    break
                i += 1
            else: problems.append((start, 'ambiguous-regex'))
            continue
        identifier = re.match(r'(?:r\#)?[A-Za-z_$][A-Za-z_0-9$]*', text[i:])
        if identifier:
            add(identifier.group(), 'identifier', start); i += identifier.end(); continue
        if text.startswith('::', i): add('::', 'punctuation', start); i += 2; continue
        add(text[i], 'punctuation', start); i += 1
    return tokens, problems


def extract(text: str, language: str, ranges=None):
    if language == 'Python':
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            return [], [{'line': exc.lineno or 1, 'reason': 'syntax-error'}]
        refs = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                refs.extend({'kind': 'import', 'specifier': alias.name, 'line': node.lineno, 'column': node.col_offset + 1} for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                refs.append({'kind': 'import', 'specifier': '.' * node.level + (node.module or ''), 'line': node.lineno, 'column': node.col_offset + 1})
        return refs, []
    tokens, problems = tokenize(text, language, jsx=ranges is None)
    if ranges is not None and language in {'JSX', 'TSX'}:
        # Preserve explicit markup-expression uncertainty in both adapters.
        problems.extend(tokenize(text, language, jsx=True)[1])
    refs = []; unknowns = [{'line': text.count('\n', 0, pos) + 1, 'reason': reason} for pos, reason in problems]
    contexts = {}; stack = []; context = []
    if language == 'Rust':
        for index, item in enumerate(tokens):
            contexts[item.start] = list(context)
            if item.value == '{':
                stack.append(list(context))
                if index >= 2 and tokens[index - 2].value == 'mod': context.append(tokens[index - 1].value)
            elif item.value == '}' and stack: context = stack.pop()
    def emit(token, kind, specifier):
        if ranges is None or any(a <= token.start < b for a, b in ranges):
            ref = {'kind': kind, 'specifier': specifier, 'line': token.line, 'column': token.column}
            if language == 'Rust': ref['context'] = contexts.get(token.start, [])
            refs.append(ref)
    def unknown(token, reason): unknowns.append({'line': token.line, 'reason': reason})
    def value(index): return tokens[index].value if index < len(tokens) else ''
    def literal(index): return index < len(tokens) and tokens[index].kind == 'string'
    for i, token in enumerate(tokens):
        if token.kind != 'identifier': continue
        name = token.value
        if language != 'Rust':
            if i and value(i - 1) in {'.', '?'}: continue
            if name in {'require', 'import'} and value(i + 1) == '(':
                if literal(i + 2) and value(i + 3) == ')':
                    emit(token, 'require' if name == 'require' else 'dynamic-import', value(i + 2))
                else: unknown(token, 'computed-module-path')
            elif name == 'import' and value(i + 1) == '.':
                unknown(token, 'import-meta-runtime')
            elif name == 'import' and literal(i + 1): emit(token, 'import', value(i + 1))
            elif name in {'import', 'export'} and (name == 'import' or value(i + 1) in {'type', '*', '{'}):
                kind = 'type-import' if name == 'import' and value(i + 1) == 'type' else name
                for j in range(i + 1, min(len(tokens), i + 256)):
                    if value(j) == ';' or value(j) in {'import', 'export'}: break
                    if value(j) == 'from' and literal(j + 1):
                        emit(token, kind, value(j + 1)); break
                else: unknown(token, 'unsupported-module-declaration')
        else:
            if name == 'mod' and i + 2 < len(tokens) and tokens[i + 1].kind == 'identifier':
                if value(i + 2) == ';':
                    path = None
                    for j in range(max(0, i - 14), i):
                        if value(j) in {';', '{', '}'}: path = None
                        if value(j) == 'path' and value(j + 1) == '=' and literal(j + 2): path = value(j + 2)
                    emit(token, 'path' if path else 'mod', path or value(i + 1))
            elif name == 'use':
                parts = []
                for j in range(i + 1, min(len(tokens), i + 256)):
                    if value(j) == ';': break
                    parts.append(value(j))
                else: unknown(token, 'unsupported-use-tree')
                def expand(items, prefix=''):
                    if '{' not in items:
                        if 'as' in items: items = items[:items.index('as')]
                        return [prefix + ''.join(items)] if items else []
                    opening = items.index('{'); base = prefix + ''.join(items[:opening])
                    children = []; depth = 0; begin = opening + 1
                    for index in range(begin, len(items)):
                        item = items[index]
                        if item == '{': depth += 1
                        elif item == '}' and depth: depth -= 1
                        elif item in {',', '}'} and depth == 0:
                            children.extend(expand(items[begin:index], base)); begin = index + 1
                            if item == '}': break
                    return children
                for specifier in expand(parts):
                    if specifier.endswith('::self'): specifier = specifier[:-6]
                    emit(token, 'use', specifier)
            elif name in {'include', 'include_str', 'include_bytes'} and value(i + 1) == '!':
                if value(i + 2) == '(' and literal(i + 3) and value(i + 4) == ')': emit(token, 'include', value(i + 3))
                else: unknown(token, 'computed-include-path')
            elif name in {'cfg', 'cfg_attr'} and i and value(i - 1) == '[': unknown(token, 'conditional-compilation')
            elif name == 'derive' and i and value(i - 1) == '[': unknown(token, 'unexpanded-attribute')
            elif value(i + 1) == '!': unknown(token, 'unexpanded-macro')
    # Inline module location affects filesystem resolution even when parsing succeeds.
    if language == 'Rust' and re.search(r'\bmod\s+\w+\s*\{', text):
        unknowns.append({'line': 1, 'reason': 'inline-module-context'})
    unique = {(r['kind'], r['specifier'], r['line'], r['column']): r for r in refs}
    return sorted(unique.values(), key=lambda r: (r['line'], r['column'], r['kind'])), unknowns


def _ast_ranges(executable: str, files: list[Path], root: Path, timeout: float):
    rules = []
    for language in ['JavaScript', 'TypeScript', 'Tsx', 'Rust']:
        kinds = ['mod_item', 'use_declaration', 'macro_invocation', 'attribute_item'] if language == 'Rust' else ['import_statement', 'export_statement', 'call_expression']
        rules.append('id: dependencies-' + language.lower() + '\nlanguage: ' + language + '\nrule:\n  any:\n' + ''.join('    - kind: ' + kind + '\n' for kind in kinds))
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        result = subprocess.run([executable, 'scan', '--inline-rules', '\n---\n'.join(rules), '--json=compact', *map(str, files)], cwd=root, stdout=out, stderr=err, timeout=timeout, check=False)
        if out.tell() > MAX_OUTPUT_BYTES or err.tell() > MAX_OUTPUT_BYTES: raise ValueError('ast-output-limit')
        out.seek(0); err.seek(0)
        if result.returncode != 0: raise ValueError('ast-scan-failed')
        data = json.load(out)
        if not isinstance(data, list): raise ValueError('ast-invalid-output')
    ranges = {path: [] for path in files}
    source_bytes = {path: path.read_bytes() for path in files}
    for match in data:
        path = Path(match['file'])
        if not path.is_absolute(): path = root / path
        path = path.resolve()
        if path not in ranges: raise ValueError('ast-out-of-scope-output')
        span = match['range']['byteOffset']
        # ast-grep offsets are UTF-8 bytes; fallback lexer offsets are characters.
        raw = source_bytes[path]
        if type(span['start']) is not int or type(span['end']) is not int or not 0 <= span['start'] < span['end'] <= len(raw):
            raise ValueError('ast-invalid-range')
        ranges[path].append((len(raw[:span['start']].decode()), len(raw[:span['end']].decode())))
    return ranges


def _provider(mode: str):
    if mode not in {'auto', 'python', 'ast-grep'}: raise ValueError('Unknown dependency provider')
    diagnostics = []; executable = None; version = VERSION
    if mode != 'python':
        for name in ['ast-grep', 'sg']:
            candidate = shutil.which(name)
            if not candidate: continue
            try:
                result = subprocess.run([candidate, '--version'], capture_output=True, timeout=2, check=False)
                match = re.fullmatch(rb'ast-grep (\d+\.\d+\.\d+)(?:[^\n]*)\n?', result.stdout)
                if result.returncode == 0 and match:
                    executable = candidate; version = match.group(1).decode(); break
                diagnostics.append({'reason': 'incompatible-executable', 'name': name})
            except (OSError, subprocess.TimeoutExpired): diagnostics.append({'reason': 'provider-probe-failed', 'name': name})
        if not executable: diagnostics.append({'reason': 'ast-grep-unavailable'})
    return executable, version, diagnostics


def _read_config(root: Path, sources=()):
    configs = {}; parsed = {}; diagnostics = []
    names = set(CONFIG_NAMES)
    for source in sources:
        for parent in source.relative_to(root).parents:
            names.update((parent / name).as_posix() for name in CONFIG_NAMES)
    for name in sorted(names):
        if not (root / name).exists(): continue
        try:
            path = safe_file(root, name)
            if path.stat().st_size > MAX_FILE_BYTES: raise ValueError('config-size-limit')
            raw = path.read_bytes(); configs[name] = hashlib.sha256(raw).hexdigest()
            if name.endswith('.json'):
                parsed[name] = json.loads(raw)
                if not isinstance(parsed[name], dict): raise ValueError('invalid-config-object')
                options = parsed[name].get('compilerOptions', {})
                if not isinstance(options, dict) or not isinstance(options.get('paths', {}), dict) or not isinstance(options.get('baseUrl', '.'), str): raise ValueError('invalid-module-options')
                for alias, targets in options.get('paths', {}).items():
                    if not isinstance(alias, str) or alias.count('*') > 1 or not isinstance(targets, list) or any(not isinstance(target, str) or target.count('*') > 1 for target in targets):
                        raise ValueError('invalid-module-paths')
                if parsed[name].get('extends'): diagnostics.append({'file': name, 'reason': 'inherited-config-unresolved'})
        except (ValueError, OSError, UnicodeError) as exc:
            parsed.pop(name, None)
            diagnostics.append({'file': name, 'reason': 'unsupported-or-unreadable-config'})
    return configs, parsed, diagnostics


def _rust_items(tokens, depth=0):
    """Read module-level declarations; skip function/impl/macro bodies."""
    modules = []; symbols = set(); aliases = set(); attributes = []
    i = 0
    def value(index): return tokens[index].value if index < len(tokens) else ''
    def close(index, opening, closing):
        nesting = 0
        for end in range(index, len(tokens)):
            item = tokens[end]
            if item.kind != 'punctuation': continue
            if item.value == opening: nesting += 1
            elif item.value == closing:
                nesting -= 1
                if nesting == 0: return end
        raise ValueError('rust-unbalanced-module-source')
    if depth > MAX_RUST_MODULE_DEPTH: raise ValueError('rust-module-depth-limit')
    while i < len(tokens):
        item = tokens[i]
        if item.kind == 'punctuation' and item.value == '#' and value(i + 1) in {'[', '!'}:
            begin = i + 2 if value(i + 1) == '!' else i + 1
            if value(begin) != '[': raise ValueError('rust-invalid-attribute')
            end = close(begin, '[', ']'); attributes.extend(tokens[begin + 1:end]); i = end + 1; continue
        if item.kind == 'identifier' and item.value == 'mod' and i + 2 < len(tokens) and tokens[i + 1].kind == 'identifier':
            name = value(i + 1).removeprefix('r#'); form = value(i + 2)
            path = None; conditional_path = False
            for n, attribute in enumerate(attributes):
                if attribute.value == 'cfg_attr' and any(t.value == 'path' for t in attributes[n:]): conditional_path = True
                if attribute.value == 'path' and n + 2 < len(attributes) and attributes[n + 1].value == '=' and attributes[n + 2].kind == 'string': path = attributes[n + 2].value
            if form in {';', '{'}:
                body = None
                if form == '{':
                    end = close(i + 2, '{', '}'); body = _rust_items(tokens[i + 3:end], depth + 1); i = end + 1
                else: i += 3
                modules.append({'name': name, 'path': path, 'conditional_path': conditional_path, 'body': body})
                attributes = []; continue
        if item.kind == 'identifier' and item.value in {'fn', 'struct', 'enum', 'trait', 'type', 'const', 'static', 'union'}:
            if i + 1 < len(tokens) and tokens[i + 1].kind == 'identifier': symbols.add(value(i + 1).removeprefix('r#'))
        if item.kind == 'identifier' and item.value == 'use':
            # Names introduced by imports/re-exports require symbol resolution.
            # Mark them uncertain rather than assigning them to the import file.
            end = i + 1
            while end < len(tokens) and value(end) != ';': end += 1
            aliases.update(t.value.removeprefix('r#') for t in tokens[i + 1:end] if t.kind == 'identifier')
            i = end; attributes = []
        if i < len(tokens) and tokens[i].kind == 'punctuation':
            if value(i) in {'{', '('}:
                i = close(i, value(i), '}' if value(i) == '{' else ')') + 1
                attributes = []; continue
            if value(i) == ';': attributes = []
        i += 1
    return {'modules': modules, 'symbols': symbols, 'aliases': aliases}


class RustModules:
    """Bounded module ownership projection; never execute Rust/Cargo code."""
    def __init__(self, root, observed, diagnostics):
        self.root = root; self.observed = observed; self.diagnostics = diagnostics
        self.cache = {}; self.trees = {}; self.total_bytes = 0; self.failed = False

    def read(self, relative):
        try: relative = (self.root / relative).resolve().relative_to(self.root).as_posix()
        except (ValueError, OSError): return None
        if relative in self.cache: return relative, self.cache[relative]
        try:
            path = safe_file(self.root, relative)
            if len(self.cache) >= MAX_RUST_MODULE_FILES: raise ValueError('rust-module-file-limit')
            if path.stat().st_size > MAX_FILE_BYTES or self.total_bytes + path.stat().st_size > MAX_RUST_MODULE_BYTES: raise ValueError('rust-module-size-limit')
            raw = path.read_bytes(); self.total_bytes += len(raw)
            self.observed.setdefault(relative, hashlib.sha256(raw).hexdigest())
            text = raw.decode('utf-8'); tokens, problems = tokenize(text, 'Rust')
            if problems: raise ValueError('rust-module-lexical-uncertainty')
            parsed = _rust_items(tokens)
            self.cache[relative] = parsed
            return relative, parsed
        except (ValueError, OSError, UnicodeError) as exc:
            if (self.root / relative).exists():
                self.failed = True
                self.diagnostics.append({'file': relative, 'reason': 'rust-module-index-incomplete', 'detail': str(exc) if isinstance(exc, ValueError) else type(exc).__name__})
            return None

    def tree(self, entry):
        if entry in self.trees: return self.trees[entry]
        nodes = {}; by_file = {}
        def build(relative, parsed, logical, directory, active, depth):
            if depth > MAX_RUST_MODULE_DEPTH or relative in active:
                self.failed = True
                self.diagnostics.append({'file': relative, 'reason': 'rust-module-index-incomplete', 'detail': 'depth-limit-or-cycle'})
                return
            node = {'file': relative, 'symbols': parsed['symbols'], 'aliases': parsed['aliases'], 'children': {}}
            nodes[logical] = node; by_file.setdefault(relative, []).append(logical)
            for module in parsed['modules']:
                name = module['name']; child = logical + (name,)
                if name in node['children']:
                    node['children'][name] = None
                    nodes.pop(child, None); continue
                node['children'][name] = None
                if module['conditional_path']: continue
                if module['body'] is not None:
                    base = Path(relative).parent / module['path'] if module['path'] else directory / name
                    build(relative, module['body'], child, base, active, depth + 1)
                else:
                    candidates = [Path(relative).parent / module['path']] if module['path'] else [directory / (name + '.rs'), directory / name / 'mod.rs']
                    available = [self.read(path) for path in candidates]
                    available = [value for value in available if value is not None]
                    if len(available) != 1: continue
                    path, content = available[0]
                    base = Path(path).parent if Path(path).name == 'mod.rs' else Path(path).with_suffix('')
                    build(path, content, child, base, active | {relative}, depth + 1)
                if child in nodes: node['children'][name] = child
        loaded = self.read(entry)
        if loaded is not None:
            relative, parsed = loaded
            build(relative, parsed, (), Path(relative).parent, set(), 0)
        self.trees[entry] = (nodes, by_file)
        return nodes, by_file

    def resolve(self, source, ref, crate):
        manifest = self.root / crate / 'Cargo.toml'
        if manifest.is_file():
            try:
                content = safe_file(self.root, (crate / 'Cargo.toml').as_posix()).read_text(encoding='utf-8')
                if re.search(r'(?m)^\s*(?:autolib|autobins)\s*=\s*false\b', content) or re.search(r'(?ms)^\s*\[\[?(?:lib|bin)\]\]?.*?^\s*path\s*=', content):
                    return None, 'rust-custom-crate-root-unresolved'
            except (OSError, ValueError, UnicodeError): return None, 'rust-crate-config-unresolved'
        parts = [part.removeprefix('r#') for part in ref['specifier'].split('::') if part]
        if not parts or any(not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*|\*', part) for part in parts): return None, 'unsupported-use-tree'
        owners = set(); uncertain = False
        for entry in [crate / 'src/lib.rs', crate / 'src/main.rs']:
            nodes, by_file = self.tree(entry)
            # Same physical file may have several module declarations. Resolve
            # each possible logical context; disagreement remains ambiguous.
            for logical in by_file.get(source, []):
                if logical not in nodes: uncertain = True; continue
                if logical and nodes[logical]['file'] == nodes.get(logical[:-1], {}).get('file'):
                    continue  # Context below adds inline nesting once.
                current = logical + tuple(name.removeprefix('r#') for name in ref.get('context', []))
                if current not in nodes: uncertain = True; continue
                rest = list(parts)
                if rest[0] == 'crate': current = (); rest.pop(0)
                elif rest[0] == 'self': rest.pop(0)
                elif rest[0] == 'super':
                    while rest and rest[0] == 'super':
                        if not current: uncertain = True; break
                        current = current[:-1]; rest.pop(0)
                    if rest and rest[0] == 'super': continue
                else: current = ()
                while rest and rest[0] != '*':
                    node = nodes.get(current)
                    if node is None: uncertain = True; break
                    segment = rest.pop(0)
                    if segment in node['children']:
                        child = node['children'][segment]
                        if child is None: uncertain = True; break
                        current = child
                    elif segment in node['aliases']:
                        uncertain = True; break
                    elif segment in node['symbols'] and not rest:
                        break
                    else: uncertain = True; break
                else:
                    if rest not in [[], ['*']]: uncertain = True
                if not uncertain and current in nodes: owners.add(nodes[current]['file'])
        if len(owners) == 1 and not uncertain: return owners.pop(), None
        return None, 'ambiguous-module-resolution' if len(owners) > 1 else 'rust-module-ownership-unresolved'


def _resolve(root: Path, source: str, ref: dict, language: str, config: dict, observed=None, rust=None):
    spec = ref['specifier']; parent = Path(source).parent
    candidates = []
    if language in {'JS', 'JSX', 'TS', 'TSX'}:
        if spec.startswith('.'):
            bases = [parent / spec]
        else:
            settings = {}; config_parent = Path('.')
            for directory in [parent, *parent.parents]:
                found = next((name for name in ['tsconfig.json', 'jsconfig.json'] if (directory / name).as_posix() in config), None)
                if found:
                    settings = config[(directory / found).as_posix()]; config_parent = directory; break
            options = settings.get('compilerOptions', {})
            bases = []
            for alias, targets in options.get('paths', {}).items():
                pattern = '^' + re.escape(alias).replace(r'\*', '(.*)') + '$'
                match = re.match(pattern, spec)
                if match and isinstance(targets, list):
                    bases.extend(config_parent / Path(options.get('baseUrl', '.')) / target.replace('*', match.group(1) if match.groups() else '') for target in targets if isinstance(target, str))
            if not bases: return None, 'external-or-unresolved-module'
        for base in bases:
            # .js specifiers commonly resolve to .ts implementations under TS.
            candidates.append(base)
            if language in {'TS', 'TSX'} and base.suffix in {'.js', '.jsx', '.mjs', '.cjs'}:
                candidates.extend(base.with_suffix(ext) for ext in ['.ts', '.tsx', '.mts', '.cts'])
            if not base.suffix:
                candidates.extend(Path(str(base) + ext) for ext in ['.ts', '.tsx', '.js', '.jsx', '.mts', '.cts', '.mjs', '.cjs'])
                candidates.extend(base / ('index' + ext) for ext in ['.ts', '.tsx', '.js', '.jsx'])
    elif language == 'Rust':
        crate = Path('.')
        for directory in [parent, *parent.parents]:
            if (root / directory / 'Cargo.toml').is_file(): crate = directory; break
        owner = parent if Path(source).name in {'lib.rs', 'main.rs', 'mod.rs'} else parent / Path(source).stem
        context = ref.get('context', [])
        if ref['kind'] == 'use' and rust is not None:
            return rust.resolve(source, ref, crate)
        if ref['kind'] == 'mod': spec = spec.removeprefix('r#')
        if ref['kind'] in {'path', 'include'}:
            candidates = [(owner.joinpath(*context) if context else parent) / spec]
        elif ref['kind'] == 'mod':
            base = owner.joinpath(*context)
            candidates = [base / (spec + '.rs'), base / spec / 'mod.rs']
        else:
            if '{' in spec: spec = spec.split('{')[0].rstrip(':')
            spec = spec.split('as')[0].rstrip(':') if ' as ' in ref['specifier'] else spec
            parts = [part for part in spec.split('::') if part and part != '*']
            if not parts: return None, 'unsupported-use-tree'
            if parts[0] == 'crate': base = crate / 'src'; parts = parts[1:]
            elif parts[0] == 'self': base = owner.joinpath(*context); parts = parts[1:]
            elif parts[0] == 'super':
                base = owner.joinpath(*context)
                while parts and parts[0] == 'super': base = base.parent; parts = parts[1:]
            else: base = crate / 'src'
            for length in range(len(parts), 0, -1):
                stem = base.joinpath(*parts[:length]); candidates.extend([Path(str(stem) + '.rs'), stem / 'mod.rs'])
    elif language == 'Python':
        count = len(spec) - len(spec.lstrip('.')); name = spec.lstrip('.').replace('.', '/')
        base = parent
        for _ in range(max(0, count - 1)): base = base.parent
        base = base / name if count else Path(name)
        candidates = [Path(str(base) + '.py'), base / '__init__.py']
    existing = []
    for candidate in candidates:
        try:
            normalized = (root / candidate).resolve().relative_to(root).as_posix()
            resolved = safe_file(root, normalized).relative_to(root).as_posix()
            if resolved not in existing: existing.append(resolved)
            if observed is not None:
                path = safe_file(root, resolved)
                if path.stat().st_size > MAX_FILE_BYTES: raise ValueError('dependency-size-limit')
                observed.setdefault(resolved, hashlib.sha256(path.read_bytes()).hexdigest())
        except (ValueError, OSError): continue
    if len(existing) == 1: return existing[0], None
    return None, 'ambiguous-module-resolution' if existing else 'unresolved-module'


def analyze_dependencies(root: Path, files, *, provider='python', limit=1000, timeout=10):
    root = root.resolve()
    if not 1 <= limit <= 10000 or not 0 < timeout <= 60: raise ValueError('Invalid analysis bounds')
    selected = sorted(set(files)); diagnostics = []; paths = []; skipped = []; total_bytes = 0
    for relative in selected[:limit]:
        try:
            path = safe_file(root, relative)
            if path.suffix not in LANGUAGES: skipped.append({'file': relative, 'reason': 'unsupported-language'}); continue
            if path.stat().st_size > MAX_FILE_BYTES: raise ValueError('source-size-limit')
            total_bytes += path.stat().st_size
            if total_bytes > MAX_TOTAL_BYTES: raise ValueError('total-source-size-limit')
            paths.append(path)
        except (ValueError, OSError): skipped.append({'file': relative, 'reason': 'unreadable-or-out-of-scope'})
    before = {}
    for path in paths:
        try: before[path] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError: skipped.append({'file': path.relative_to(root).as_posix(), 'reason': 'source-read-failed'})
    paths = list(before)
    executable, version, discovery = _provider(provider); diagnostics.extend(discovery)
    ranges = None
    ast_paths = [path for path in paths if path.suffix != '.py']
    if executable and ast_paths:
        try: ranges = _ast_ranges(executable, ast_paths, root, timeout)
        except (OSError, ValueError, KeyError, TypeError, UnicodeError, subprocess.TimeoutExpired) as exc:
            diagnostics.append({'reason': 'ast-grep-fallback', 'failure': type(exc).__name__,
                                'detail': str(exc) if isinstance(exc, ValueError) else type(exc).__name__})
            executable = None; version = VERSION
    actual_provider = 'ast-grep' if executable and ast_paths else 'python'
    if actual_provider == 'python': version = VERSION
    hashes, config, config_problems = _read_config(root, paths); diagnostics.extend(config_problems)
    references = []; edges = []; unknowns = []; scanned = []; identities = dict(hashes)
    rust = RustModules(root, identities, diagnostics)
    for path in paths:
        relative = path.relative_to(root).as_posix(); language = LANGUAGES[path.suffix]
        try:
            raw = path.read_bytes(); identities[relative] = hashlib.sha256(raw).hexdigest()
            if identities[relative] != before[path]: diagnostics.append({'reason': 'candidate-changed-during-analysis', 'files': [relative]})
            text = raw.decode('utf-8'); refs, problems = extract(text, language, ranges.get(path, []) if ranges is not None and path in ranges else None)
            scanned.append({'file': relative, 'language': language, 'sha256': identities[relative]})
            unknowns.extend({'source': relative, 'language': language, **item} for item in problems)
            for ref in refs:
                references.append({'source': relative, 'language': language, **ref})
                target, reason = _resolve(root, relative, ref, language, config, identities, rust)
                if target:
                    edges.append({'source': relative, 'target': target, 'kind': ref['kind'], 'line': ref['line'], 'language': language})
                else: unknowns.append({'source': relative, 'language': language, 'line': ref['line'], 'specifier': ref['specifier'], 'reason': reason})
        except (ValueError, OSError, UnicodeError): skipped.append({'file': relative, 'reason': 'source-read-failed'})
    unstable = [path.relative_to(root).as_posix() for path, sha in before.items()
                if identities.get(path.relative_to(root).as_posix()) != sha]
    for relative, original in identities.items():
        try:
            if hashlib.sha256(safe_file(root, relative).read_bytes()).hexdigest() != original: unstable.append(relative)
        except (ValueError, OSError): unstable.append(relative)
    if unstable: diagnostics.append({'reason': 'candidate-changed-during-analysis', 'files': unstable})
    unknowns = [dict(items) for items in sorted({tuple(sorted(item.items())) for item in unknowns})]
    identity = {'version': VERSION, 'provider': actual_provider, 'provider_version': version,
                'files': identities, 'limit': limit, 'rules_version': VERSION}
    return {'schema': 'pyramid-dependency-analysis-v1', 'provider': actual_provider,
            'provider_version': version, 'requested_provider': provider, 'cache': 'disabled',
            'identity_sha256': digest(identity), 'inputs': identities,
            'scan': {'complete': len(selected) <= limit and not skipped and not unstable and not rust.failed,
                     'requested': len(selected), 'scanned': scanned, 'skipped': skipped,
                     'truncated': max(0, len(selected) - limit)},
            'references': references, 'edges': edges, 'unresolved': unknowns,
            'diagnostics': diagnostics, 'scope_removal_authorized': False,
            'limitations': ['Syntax references are advisory; dependency and semantic completeness are not certified.',
                            'External modules, conditional compilation and generated relationships require review.']}
