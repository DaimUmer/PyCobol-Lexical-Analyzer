"""
PyCOBOL Lexical Analyzer — Web Interface
=========================================
Flask-based web GUI for the PyCOBOL lexer.
Provides an interactive interface for source code analysis.

Course  : Theory of Programming Language (CT-367)
Language: PyCOBOL (Hybrid: COBOL + Python)
"""

from flask import Flask, render_template, request, jsonify
from collections import Counter
import os
import glob

from core.lexer import tokenize, build_symbol_table

app = Flask(__name__)


@app.route("/")
def index():
    """Serve the main analyzer page."""
    # Find all .pycobol test files in the project directory
    test_files = [os.path.basename(f) for f in sorted(glob.glob("tests/*.pycobol"))]
    return render_template("index.html", test_files=test_files)


@app.route("/analyze", methods=["POST"])
def analyze():
    """Analyze source code and return results as JSON."""
    data = request.get_json()
    source_code = data.get("source_code", "")

    if not source_code.strip():
        return jsonify({"error": "No source code provided"}), 400

    # Run the lexer
    tokens, errors = tokenize(source_code)
    symbols = build_symbol_table(tokens)

    # Build token list
    token_list = []
    for tok in tokens:
        token_list.append({
            "type": tok.token_type,
            "value": tok.value,
            "line": tok.line,
            "column": tok.column,
        })

    # Build error list
    error_list = []
    for err in errors:
        error_list.append({
            "type": err.error_type,
            "message": err.message,
            "line": err.line,
            "column": err.column,
            "fragment": err.fragment,
        })

    # Build symbol table
    symbol_list = []
    for name, entry in sorted(symbols.items(), key=lambda x: x[1].line):
        symbol_list.append({
            "name": entry.name,
            "entry_type": entry.entry_type,
            "data_type": entry.data_type,
            "value": str(entry.value),
            "scope": entry.scope,
            "line": entry.line,
        })

    # Build summary
    counts = Counter(t.token_type for t in tokens)
    summary = {k: v for k, v in sorted(counts.items())}

    # Build analysis report
    total_lines = len(source_code.splitlines())
    total_tokens = len(tokens)

    cobol_count = (
        counts.get("COBOL_KEYWORD", 0) +
        counts.get("COBOL_DIVISION", 0) +
        counts.get("COBOL_SECTION", 0) +
        counts.get("PICTURE_CLAUSE", 0)
    )
    python_count = counts.get("PYTHON_KEYWORD", 0)
    lang_total = cobol_count + python_count

    if lang_total > 0:
        cobol_pct = round((cobol_count / lang_total) * 100, 1)
        python_pct = round((python_count / lang_total) * 100, 1)
    else:
        cobol_pct = 0
        python_pct = 0

    analysis = {
        "total_lines": total_lines,
        "total_tokens": total_tokens,
        "total_errors": len(errors),
        "total_symbols": len(symbols),
        "cobol_count": cobol_count,
        "python_count": python_count,
        "cobol_pct": cobol_pct,
        "python_pct": python_pct,
        "summary": summary,
    }

    return jsonify({
        "tokens": token_list,
        "errors": error_list,
        "symbols": symbol_list,
        "analysis": analysis,
    })


@app.route("/load_file", methods=["POST"])
def load_file():
    """Load a test file and return its contents."""
    data = request.get_json()
    filename = data.get("filename", "")

    # Security: only allow .pycobol files in current directory
    if not filename.endswith(".pycobol") or os.sep in filename or "/" in filename:
        return jsonify({"error": "Invalid filename"}), 400

    try:
        with open(os.path.join("tests", filename), "r") as f:
            content = f.read()
        return jsonify({"content": content})
    except FileNotFoundError:
        return jsonify({"error": f"File '{filename}' not found"}), 404


if __name__ == "__main__":
    print("\n  PyCOBOL Lexical Analyzer — Web Interface")
    print("  Open in browser: http://127.0.0.1:5000\n")
    app.run(debug=True, port=5000)
