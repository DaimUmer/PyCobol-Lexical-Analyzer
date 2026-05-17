

import re
import sys


# Token Definition

COBOL_DIVISIONS = [
    "IDENTIFICATION DIVISION",
    "DATA DIVISION",
    "PROCEDURE DIVISION",
    "ENVIRONMENT DIVISION",
]

COBOL_SECTIONS = [
    "WORKING-STORAGE SECTION",
    "FILE SECTION",
    "LINKAGE SECTION",
    "INPUT-OUTPUT SECTION",
    "CONFIGURATION SECTION",
]

COBOL_KEYWORDS = [
    "PROGRAM-ID", "AUTHOR", "DATE-WRITTEN",
    "COMPUTE", "MOVE", "DISPLAY", "PERFORM",
    "STOP RUN", "ADD", "SUBTRACT", "MULTIPLY",
    "DIVIDE", "GIVING", "TO", "FROM", "BY",
    "UNTIL", "VARYING", "THRU", "THROUGH",
    "EVALUATE", "WHEN", "END-EVALUATE",
    "IF", "ELSE", "END-IF", "THEN",
    "OPEN", "CLOSE", "READ", "WRITE",
    "PIC", "VALUE", "FILLER",
    "01", "02", "03", "04", "05", "77", "88",
    "ACCEPT", "UNSTRING", "REDEFINES", "COPYBOOKS", "ABBEND",
    "FD", "SELECT", "ASSIGN", "ORGANIZATION", "SEQUENTIAL",
    "EXTEND", "OUTPUT", "INPUT",
    "UPON", "AT", "END", "TRIM", "WITH", "ADVANCING",
]

PYTHON_KEYWORDS = [
    "if", "else", "elif", "for", "while",
    "def", "return", "class", "import", "from",
    "in", "not", "and", "or", "is",
    "True", "False", "None",
    "print", "input", "range", "len",
    "try", "except", "finally", "raise",
    "with", "as", "pass", "break", "continue",
    "lambda", "yield", "global", "nonlocal",
]

# ─────────────────────────────────────────────
#  REGULAR EXPRESSION RULES
# ─────────────────────────────────────────────

TOKEN_RULES = [
    ("COMMENT",          r'\*.*|#.*'),
    ("UNCLOSED_STRING",  r'"[^"\n]*$|\'[^\'\n]*$'),
    ("STRING_LITERAL",   r'"[^"]*"|\'[^\']*\''),
    ("PICTURE_CLAUSE",   r'\bPIC\s+[A-Za-z0-9().V\-]+\b'),
    ("FLOAT",            r'\b\d+\.\d+\b'),
    ("INTEGER",          r'\b\d+\b'),
    ("OPERATOR",         r'==|!=|<=|>=|<|>'),
    ("OPERATOR",         r'[=+\-*/]'),
    ("PUNCTUATION",      r'[().,:\[\]]'),
    ("IDENTIFIER",       r'\b[A-Za-z_][A-Za-z0-9_\-]*\b'),
    ("WHITESPACE",       r'[ \t]+'),
    ("NEWLINE",          r'\n'),
    ("UNKNOWN",          r'.'),
]

MASTER_REGEX = re.compile(
    '|'.join(f'(?P<TOK{i}>{pattern})' for i, (_, pattern) in enumerate(TOKEN_RULES)),
    re.IGNORECASE | re.MULTILINE
)

COBOL_KEYWORD_SET  = set(k.upper() for k in COBOL_KEYWORDS)
PYTHON_KEYWORD_SET = set(k for k in PYTHON_KEYWORDS)


# ─────────────────────────────────────────────
#  TOKEN & ERROR CLASSES
# ─────────────────────────────────────────────

class Token:
    def __init__(self, token_type, value, line, column=0):
        self.token_type = token_type
        self.value      = value
        self.line       = line
        self.column     = column


class LexicalError:
    """Represents a lexical error found during scanning."""
    def __init__(self, error_type, message, line, column, fragment):
        self.error_type = error_type   # e.g. 'UNCLOSED_STRING', 'UNKNOWN_CHAR'
        self.message    = message      # Human-readable description
        self.line       = line
        self.column     = column
        self.fragment   = fragment     # The offending text


class SymbolEntry:
    """Represents an entry in the symbol table."""
    def __init__(self, name, entry_type="IDENTIFIER", data_type="--",
                 value="--", scope="GLOBAL", line=0):
        self.name       = name
        self.entry_type = entry_type   # VARIABLE, CONSTANT, FUNCTION, etc.
        self.data_type  = data_type    # From PIC clause or inferred
        self.value      = value        # Initial or assigned value
        self.scope      = scope        # GLOBAL, DATA DIVISION, PROCEDURE, etc.
        self.line       = line         # First occurrence line number


# ─────────────────────────────────────────────
#  VALID PIC CHARACTER SET
# ─────────────────────────────────────────────

VALID_PIC_CHARS = set('0123456789AXVSPBZaxvspbz().,+-')


# ─────────────────────────────────────────────
#  LEXER (with Error Detection & Recovery)
# ─────────────────────────────────────────────

def tokenize(source_code):
    tokens   = []
    errors   = []
    line_num = 1
    col_offset = 0   # tracks column position within each line

    # Build a map of line start positions for column calculation
    line_starts = [0]
    for i, ch in enumerate(source_code):
        if ch == '\n':
            line_starts.append(i + 1)

    def get_column(pos):
        """Calculate column number from absolute position."""
        for i in range(len(line_starts) - 1, -1, -1):
            if pos >= line_starts[i]:
                return pos - line_starts[i] + 1
        return 1

    # Pre-pass: collapse multi-word COBOL phrases into placeholders
    modified        = source_code
    placeholder_map = {}

    multi_word = (
        [(d, "COBOL_DIVISION") for d in COBOL_DIVISIONS] +
        [(s, "COBOL_SECTION")  for s in COBOL_SECTIONS]  +
        [("STOP RUN",           "COBOL_KEYWORD"),
        ("GO TO",              "COBOL_KEYWORD"),
        ("AT END",             "COBOL_KEYWORD"),
        ("WITH NO ADVANCING",  "COBOL_KEYWORD"),
        ("FILE-CONTROL",       "COBOL_KEYWORD"),
        ("SPECIAL-NAMES",      "COBOL_KEYWORD"),
        ("FILE STATUS",        "COBOL_KEYWORD")]
    )

    for phrase, ttype in sorted(multi_word, key=lambda x: -len(x[0])):
        safe = phrase.replace(" ", "__SP__")
        placeholder_map[safe.upper()] = (phrase, ttype)
        modified = re.sub(re.escape(phrase), safe, modified, flags=re.IGNORECASE)

    for match in MASTER_REGEX.finditer(modified):
        kind  = None
        value = match.group()
        pos   = match.start()
        col   = get_column(pos)

        for i, (name, _) in enumerate(TOKEN_RULES):
            if match.group(f'TOK{i}') is not None:
                kind = name
                break

        if kind == "WHITESPACE":
            continue
        if kind == "NEWLINE":
            line_num += 1
            continue

        # ── ERROR: Unclosed string literal ──
        if kind == "UNCLOSED_STRING":
            errors.append(LexicalError(
                error_type = "UNCLOSED_STRING",
                message    = "String literal is missing closing quote",
                line       = line_num,
                column     = col,
                fragment   = value
            ))
            # Still add it as a token so parsing can continue
            tokens.append(Token("STRING_LITERAL", value, line_num, col))
            continue

        # ── ERROR: Unknown character ──
        if kind == "UNKNOWN":
            errors.append(LexicalError(
                error_type = "UNKNOWN_CHAR",
                message    = f"Unexpected character '{value}'",
                line       = line_num,
                column     = col,
                fragment   = value
            ))
            continue

        # Restore placeholders
        if value.upper() in placeholder_map:
            orig_value, orig_type = placeholder_map[value.upper()]
            tokens.append(Token(orig_type, orig_value.upper(), line_num, col))
            continue

        # ── ERROR: Invalid PIC clause ──
        if kind == "PICTURE_CLAUSE":
            pic_part = value.split(None, 1)[1] if ' ' in value else value[3:]
            invalid_chars = set(pic_part) - VALID_PIC_CHARS
            if invalid_chars:
                errors.append(LexicalError(
                    error_type = "INVALID_PIC",
                    message    = f"Invalid character(s) {invalid_chars} in PIC clause",
                    line       = line_num,
                    column     = col,
                    fragment   = value
                ))

        # Classify identifiers (with collision resolution)
        if kind == "IDENTIFIER":
            upper_val = value.upper()
            
            is_cobol_kw = upper_val in COBOL_KEYWORD_SET
            is_python_kw = value in PYTHON_KEYWORD_SET
            
            if is_cobol_kw and is_python_kw:
                # Collision detected (e.g., "if" vs "IF")
                # Resolve using exact case: lowercase "if" is Python, otherwise COBOL
                if value == upper_val:
                    kind  = "COBOL_KEYWORD"
                    value = upper_val
                else:
                    kind  = "PYTHON_KEYWORD"
            elif is_python_kw:
                # Exact match for Python keywords (including True, False, None)
                kind  = "PYTHON_KEYWORD"
            elif is_cobol_kw:
                # COBOL keywords are case-insensitive, auto-capitalize them
                kind  = "COBOL_KEYWORD"
                value = upper_val
            else:
                kind = "IDENTIFIER"

        tokens.append(Token(kind, value, line_num, col))

    return tokens, errors


# ─────────────────────────────────────────────
#  SYMBOL TABLE BUILDER
# ─────────────────────────────────────────────

def build_symbol_table(tokens):
    """Build a symbol table by analyzing the token stream.
    
    Detects:
    - Variable declarations (from COBOL PIC clauses)
    - Variable assignments (from Python-style = )
    - Function definitions (from Python def)
    - Scope tracking (DATA DIVISION vs PROCEDURE DIVISION)
    """
    symbols = {}      # name -> SymbolEntry
    current_scope = "GLOBAL"
    current_level = None  # COBOL level number (01, 05, etc.)
    i = 0

    while i < len(tokens):
        tok = tokens[i]

        # Track scope based on divisions
        if tok.token_type == "COBOL_DIVISION":
            if "DATA" in tok.value:
                current_scope = "DATA DIVISION"
            elif "PROCEDURE" in tok.value:
                current_scope = "PROCEDURE DIVISION"
            elif "IDENTIFICATION" in tok.value:
                current_scope = "IDENTIFICATION DIVISION"
            elif "ENVIRONMENT" in tok.value:
                current_scope = "ENVIRONMENT DIVISION"

        # COBOL variable declaration: 01 var_name PIC ...
        if tok.token_type == "COBOL_KEYWORD" and tok.value in ("01","02","03","04","05"):
            current_level = tok.value
            # Next token should be the variable name
            if i + 1 < len(tokens) and tokens[i+1].token_type == "IDENTIFIER":
                var_name = tokens[i+1].value
                data_type = "--"
                init_value = "--"

                # Check for PIC clause
                if i + 2 < len(tokens) and tokens[i+2].token_type == "PICTURE_CLAUSE":
                    data_type = tokens[i+2].value

                # Check for VALUE clause
                j = i + 2
                while j < len(tokens) and j < i + 6:
                    if tokens[j].token_type == "COBOL_KEYWORD" and tokens[j].value == "VALUE":
                        if j + 1 < len(tokens):
                            init_value = tokens[j+1].value
                        break
                    j += 1

                if var_name not in symbols:
                    symbols[var_name] = SymbolEntry(
                        name       = var_name,
                        entry_type = "VARIABLE",
                        data_type  = data_type,
                        value      = init_value,
                        scope      = current_scope,
                        line       = tokens[i+1].line
                    )

        # Python-style assignment: var_name = value
        if tok.token_type == "IDENTIFIER":
            if (i + 1 < len(tokens) and
                tokens[i+1].token_type == "OPERATOR" and
                tokens[i+1].value == "=" and
                (i < 1 or tokens[i-1].token_type != "OPERATOR")):
                # Check it's not == (comparison)
                if i + 2 < len(tokens) and not (
                    tokens[i+1].value == "=" and
                    i + 2 < len(tokens) and
                    tokens[i+2].token_type == "OPERATOR" and
                    tokens[i+2].value == "="
                ):
                    var_name = tok.value
                    # Get assigned value
                    assign_val = tokens[i+2].value if i + 2 < len(tokens) else "--"
                    assign_type = tokens[i+2].token_type if i + 2 < len(tokens) else "--"

                    # Infer data type from value
                    inferred_type = "--"
                    if assign_type == "STRING_LITERAL":
                        inferred_type = "STRING"
                    elif assign_type == "INTEGER":
                        inferred_type = "INTEGER"
                    elif assign_type == "FLOAT":
                        inferred_type = "FLOAT"

                    if var_name in symbols:
                        # Update existing entry with assignment info
                        if symbols[var_name].value == "--":
                            symbols[var_name].value = assign_val
                        if symbols[var_name].data_type == "--" and inferred_type != "--":
                            symbols[var_name].data_type = inferred_type
                    else:
                        symbols[var_name] = SymbolEntry(
                            name       = var_name,
                            entry_type = "VARIABLE",
                            data_type  = inferred_type,
                            value      = assign_val,
                            scope      = current_scope,
                            line       = tok.line
                        )

        # Python function definition: def func_name
        if tok.token_type == "PYTHON_KEYWORD" and tok.value == "def":
            if i + 1 < len(tokens) and tokens[i+1].token_type == "IDENTIFIER":
                func_name = tokens[i+1].value
                if func_name not in symbols:
                    symbols[func_name] = SymbolEntry(
                        name       = func_name,
                        entry_type = "FUNCTION",
                        data_type  = "CALLABLE",
                        value      = "--",
                        scope      = current_scope,
                        line       = tokens[i+1].line
                    )

        # PROGRAM-ID: captures the program name
        if tok.token_type == "COBOL_KEYWORD" and tok.value == "PROGRAM-ID":
            # Skip the colon punctuation
            j = i + 1
            while j < len(tokens) and tokens[j].token_type == "PUNCTUATION":
                j += 1
            if j < len(tokens) and tokens[j].token_type == "IDENTIFIER":
                prog_name = tokens[j].value
                if prog_name not in symbols:
                    symbols[prog_name] = SymbolEntry(
                        name       = prog_name,
                        entry_type = "PROGRAM",
                        data_type  = "PROGRAM-ID",
                        value      = "--",
                        scope      = "IDENTIFICATION DIVISION",
                        line       = tokens[j].line
                    )

        i += 1

    return symbols


# ─────────────────────────────────────────────
#  OUTPUT
# ─────────────────────────────────────────────

def print_tokens(tokens):
    print()
    print("=" * 78)
    print("         PyCOBOL LEXICAL ANALYZER  --  TOKEN OUTPUT")
    print("=" * 78)
    print(f"  {'TOKEN TYPE':<22}  {'VALUE':<28}  {'LINE':>4}  {'COL':>4}")
    print("-" * 78)
    for tok in tokens:
        print(f"  {tok.token_type:<22}  {repr(tok.value):<28}  {tok.line:>4}  {tok.column:>4}")
    print("=" * 78)
    print(f"  Total tokens found: {len(tokens)}")
    print("=" * 78)
    print()


def print_summary(tokens):
    from collections import Counter
    counts = Counter(t.token_type for t in tokens)
    print()
    print("=" * 42)
    print("       TOKEN TYPE SUMMARY")
    print("=" * 42)
    for ttype, count in sorted(counts.items()):
        print(f"  {ttype:<24} : {count}")
    print("=" * 42)
    print()


def print_errors(errors):
    """Print a detailed, formatted report of all lexical errors."""
    if not errors:
        print()
        print("=" * 68)
        print("  [OK] NO LEXICAL ERRORS FOUND -- Source is lexically clean!")
        print("=" * 68)
        print()
        return

    print()
    print("!" * 68)
    print("       LEXICAL ERRORS DETECTED")
    print("!" * 68)
    print(f"  {'#':>3}  {'ERROR TYPE':<18}  {'LINE':>4}  {'COL':>4}  {'DESCRIPTION'}")
    print("-" * 68)

    for i, err in enumerate(errors, 1):
        print(f"  {i:>3}  {err.error_type:<18}  {err.line:>4}  {err.column:>4}  {err.message}")
        print(f"       Fragment: {repr(err.fragment)}")
        print()

    print("-" * 68)
    print(f"  Total lexical errors: {len(errors)}")
    print("!" * 68)
    print()

def print_symbol_table(symbols):
    """Print the symbol table in a formatted table."""
    print()
    print("=" * 98)
    print("         PyCOBOL SYMBOL TABLE")
    print("=" * 98)
    print(f"  {'#':>3}  {'NAME':<20}  {'TYPE':<10}  {'DATA TYPE':<16}  {'VALUE':<16}  {'SCOPE':<18}  {'LINE':>4}")
    print("-" * 98)

    if not symbols:
        print("  (No symbols found)")
    else:
        for idx, (name, entry) in enumerate(sorted(symbols.items(), key=lambda x: x[1].line), 1):
            display_val = entry.value if len(str(entry.value)) <= 14 else str(entry.value)[:14] + ".."
            display_dt  = entry.data_type if len(str(entry.data_type)) <= 14 else str(entry.data_type)[:14] + ".."
            print(f"  {idx:>3}  {name:<20}  {entry.entry_type:<10}  {display_dt:<16}  {display_val:<16}  {entry.scope:<18}  {entry.line:>4}")

    print("=" * 98)
    print(f"  Total symbols: {len(symbols)}")
    print("=" * 98)
    print()


# ─────────────────────────────────────────────
#  ANALYSIS REPORT (with Hybrid Score)
# ─────────────────────────────────────────────

def print_analysis_report(tokens, source_code, errors):
    """Print a comprehensive analysis report with hybrid language scoring."""
    from collections import Counter
    counts = Counter(t.token_type for t in tokens)

    total_lines   = len(source_code.splitlines())
    total_tokens  = len(tokens)
    total_errors  = len(errors)

    # Count language-specific tokens
    cobol_count = (
        counts.get("COBOL_KEYWORD", 0) +
        counts.get("COBOL_DIVISION", 0) +
        counts.get("COBOL_SECTION", 0) +
        counts.get("PICTURE_CLAUSE", 0)
    )
    python_count = counts.get("PYTHON_KEYWORD", 0)
    lang_total   = cobol_count + python_count

    # Calculate hybrid percentages
    if lang_total > 0:
        cobol_pct  = (cobol_count / lang_total) * 100
        python_pct = (python_count / lang_total) * 100
    else:
        cobol_pct  = 0
        python_pct = 0

    # Build the hybrid score bar
    bar_len    = 30
    cobol_bar  = int(round(cobol_pct / 100 * bar_len))
    python_bar = bar_len - cobol_bar
    bar_visual = "#" * cobol_bar + "." * python_bar

    print()
    print("=" * 58)
    print("       PyCOBOL ANALYSIS REPORT")
    print("=" * 58)
    print(f"  Total Lines         : {total_lines}")
    print(f"  Total Tokens        : {total_tokens}")
    print(f"  Lexical Errors      : {total_errors}")
    print("-" * 58)
    print(f"  COBOL Keywords      : {counts.get('COBOL_KEYWORD', 0):>4}  ({counts.get('COBOL_KEYWORD', 0)/total_tokens*100:>5.1f}%)" if total_tokens else "")
    print(f"  COBOL Divisions     : {counts.get('COBOL_DIVISION', 0):>4}  ({counts.get('COBOL_DIVISION', 0)/total_tokens*100:>5.1f}%)" if total_tokens else "")
    print(f"  COBOL Sections      : {counts.get('COBOL_SECTION', 0):>4}  ({counts.get('COBOL_SECTION', 0)/total_tokens*100:>5.1f}%)" if total_tokens else "")
    print(f"  Picture Clauses     : {counts.get('PICTURE_CLAUSE', 0):>4}  ({counts.get('PICTURE_CLAUSE', 0)/total_tokens*100:>5.1f}%)" if total_tokens else "")
    print(f"  Python Keywords     : {counts.get('PYTHON_KEYWORD', 0):>4}  ({counts.get('PYTHON_KEYWORD', 0)/total_tokens*100:>5.1f}%)" if total_tokens else "")
    print(f"  Identifiers         : {counts.get('IDENTIFIER', 0):>4}  ({counts.get('IDENTIFIER', 0)/total_tokens*100:>5.1f}%)" if total_tokens else "")
    print(f"  String Literals     : {counts.get('STRING_LITERAL', 0):>4}  ({counts.get('STRING_LITERAL', 0)/total_tokens*100:>5.1f}%)" if total_tokens else "")
    print(f"  Operators           : {counts.get('OPERATOR', 0):>4}  ({counts.get('OPERATOR', 0)/total_tokens*100:>5.1f}%)" if total_tokens else "")
    print(f"  Integers            : {counts.get('INTEGER', 0):>4}  ({counts.get('INTEGER', 0)/total_tokens*100:>5.1f}%)" if total_tokens else "")
    print(f"  Floats              : {counts.get('FLOAT', 0):>4}  ({counts.get('FLOAT', 0)/total_tokens*100:>5.1f}%)" if total_tokens else "")
    print(f"  Comments            : {counts.get('COMMENT', 0):>4}  ({counts.get('COMMENT', 0)/total_tokens*100:>5.1f}%)" if total_tokens else "")
    print(f"  Punctuation         : {counts.get('PUNCTUATION', 0):>4}  ({counts.get('PUNCTUATION', 0)/total_tokens*100:>5.1f}%)" if total_tokens else "")
    print("-" * 58)
    print(f"  HYBRID SCORE:")
    print(f"    COBOL constructs  : {cobol_count:>4}  ({cobol_pct:>5.1f}%)")
    print(f"    Python constructs : {python_count:>4}  ({python_pct:>5.1f}%)")
    print(f"    [{bar_visual}]")
    print(f"    Result: {cobol_pct:.0f}% COBOL / {python_pct:.0f}% Python")
    print("=" * 58)
    print()


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("\nUsage: python lexer.py <source_file>")
        print("Example: python lexer.py test_input.pycobol\n")
        sys.exit(1)

    filename = sys.argv[1]
    try:
        with open(filename, "r") as f:
            source_code = f.read()
    except FileNotFoundError:
        print(f"\nError: File '{filename}' not found.\n")
        sys.exit(1)

    print(f"\nAnalyzing file: {filename}")
    print(f"\nSource Code:\n{'-'*68}")
    for i, line in enumerate(source_code.splitlines(), 1):
        print(f"  {i:>3} | {line}")
    print(f"{'-'*68}")

    tokens, errors = tokenize(source_code)
    symbols = build_symbol_table(tokens)
    print_tokens(tokens)
    print_summary(tokens)
    print_symbol_table(symbols)
    print_errors(errors)
    print_analysis_report(tokens, source_code, errors)


if __name__ == "__main__":
    main()