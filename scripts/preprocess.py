#!/usr/bin/env python3
"""
Converts LaTeX source (main.tex + chapter inputs) into Pandoc Markdown.

Key transformations:
  - Inlines \\input{} files recursively
  - Strips LaTeX preamble / document wrapper
  - Converts tcolorbox → Pandoc fenced divs  ::: {.box .COLOR data-title="TITLE"}
  - Converts tikzpicture → placeholder images (pre-render separately)
  - Converts section commands → Markdown headings
  - Converts \\includegraphics → Markdown images
  - Strips % comments

Usage:
  python3 scripts/preprocess.py src/main.tex build/processed.md
"""
import os
import re
import sys


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def strip_comments(text):
    """Remove % comments (skipping \\%)."""
    result = []
    i = 0
    while i < len(text):
        c = text[i]
        if c == '\\' and i + 1 < len(text):
            result.append(c)
            result.append(text[i + 1])
            i += 2
        elif c == '%':
            while i < len(text) and text[i] != '\n':
                i += 1
        else:
            result.append(c)
            i += 1
    return ''.join(result)


def resolve_inputs(text, base_dir):
    """Recursively inline \\input{file} commands."""
    def replace(m):
        fname = m.group(1).strip()
        if not fname.endswith('.tex'):
            fname += '.tex'
        fpath = os.path.join(base_dir, fname)
        if not os.path.exists(fpath):
            return f'\n<!-- input not found: {fname} -->\n'
        content = strip_comments(read_file(fpath))
        return resolve_inputs(content, base_dir)
    return re.sub(r'\\input\{([^}]+)\}', replace, text)


# ---------------------------------------------------------------------------
# Bracket / brace helpers
# ---------------------------------------------------------------------------

def read_balanced(text, pos, open_char, close_char):
    """Read balanced open_char...close_char starting at pos.
    Returns (inner_content, position_after_close).
    pos must point at open_char."""
    assert text[pos] == open_char, f"Expected '{open_char}' at pos {pos}, got '{text[pos]}'"
    depth = 0
    i = pos
    while i < len(text):
        if text[i] == open_char:
            depth += 1
        elif text[i] == close_char:
            depth -= 1
            if depth == 0:
                return text[pos + 1:i], i + 1
        i += 1
    return text[pos + 1:], len(text)


def find_env_end(text, pos, env_name):
    """Find the \\end{env_name} that matches the already-opened env.
    Returns (content, pos_after_end).  Handles nesting."""
    begin_re = re.compile(r'\\begin\s*\{' + re.escape(env_name) + r'\}')
    end_str   = r'\end{' + env_name + '}'
    depth     = 1
    i         = pos
    while i < len(text) and depth > 0:
        m_end   = text.find(end_str, i)
        m_begin = begin_re.search(text, i)
        if m_end == -1:
            return text[pos:], len(text)
        nb = m_begin.start() if m_begin else len(text)
        if nb < m_end:
            depth += 1
            i = nb + len(m_begin.group())
        else:
            depth -= 1
            if depth == 0:
                return text[pos:m_end], m_end + len(end_str)
            i = m_end + len(end_str)
    return text[pos:], len(text)


# ---------------------------------------------------------------------------
# tcolorbox → fenced div
# ---------------------------------------------------------------------------

def parse_box_options(opts):
    """Return (color, title) from a tcolorbox option string."""
    opts_lower = opts.lower()

    color = 'blue'
    if re.search(r'colback\s*=\s*green', opts_lower):
        color = 'green'
    elif re.search(r'colback\s*=\s*red', opts_lower):
        color = 'red'
    elif re.search(r'colframe\s*=\s*[a-z!0-9]*green', opts_lower):
        color = 'green'
    elif re.search(r'colframe\s*=\s*[a-z!0-9]*red', opts_lower):
        color = 'red'

    # title= may span to end of line or end at comma; strip % comments already done
    title_m = re.search(r'\btitle\s*=\s*(.*?)(?:,\s*\n|,\s*(?=[a-z])|$)', opts,
                        re.IGNORECASE | re.MULTILINE)
    if not title_m:
        title_m = re.search(r'\btitle\s*=\s*(.+)', opts, re.IGNORECASE)
    if title_m:
        title = title_m.group(1).strip().rstrip(',').strip()
        # Strip common LaTeX formatting from title text
        title = re.sub(r'\\textbf\{([^}]*)\}', r'\1', title)
        title = re.sub(r'\\textit\{([^}]*)\}', r'\1', title)
        title = re.sub(r'\\emph\{([^}]*)\}',   r'\1', title)
        title = re.sub(r'\\bfseries\b', '', title)
        title = re.sub(r'\\quad\s*', ' ', title)
        # Remove the "[click to expand/collapse]" suffix from collapsiblebox
        title = re.sub(r'\\footnotesize.*', '', title)
        title = title.strip()
    else:
        title = 'Box'

    return color, title


def convert_tcolorboxes(text):
    """Replace tcolorbox environments with Pandoc fenced divs."""
    result = []
    i = 0
    begin_re = re.compile(r'\\begin\s*\{tcolorbox\}')

    while i < len(text):
        m = begin_re.search(text, i)
        if not m:
            result.append(text[i:])
            break

        result.append(text[i:m.start()])
        after_begin = m.end()

        # Skip optional whitespace, then read [...] options if present
        j = after_begin
        while j < len(text) and text[j] in ' \t\n':
            j += 1

        opts = ''
        if j < len(text) and text[j] == '[':
            opts, j = read_balanced(text, j, '[', ']')

        color, title = parse_box_options(opts)

        # Read content until matching \end{tcolorbox}
        content, after_end = find_env_end(text, j, 'tcolorbox')

        # Recursively handle nested tcolorboxes in content
        content = convert_tcolorboxes(content)

        # Escape double-quotes in title for HTML attribute
        title_attr = title.replace('"', '&quot;')

        result.append(f'\n::: {{.box .{color} data-title="{title_attr}"}}\n')
        result.append(content.strip('\n'))
        result.append('\n:::\n')

        i = after_end

    return ''.join(result)


# ---------------------------------------------------------------------------
# tikzpicture → placeholder
# ---------------------------------------------------------------------------

_tikz_count = 0

def convert_tikz(text):
    global _tikz_count

    def replace(m):
        global _tikz_count
        _tikz_count += 1
        n = _tikz_count
        return (
            f'\n![Tikz figure {n}: pgfplots chart]'
            f'(images/tikz_{n}.svg){{.tikz-placeholder}}\n'
        )

    return re.sub(
        r'\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}',
        replace, text, flags=re.DOTALL
    )


# ---------------------------------------------------------------------------
# figures / includegraphics
# ---------------------------------------------------------------------------

def convert_figures(text):
    # \includegraphics[opts]{path} → ![](images/basename)
    def fix_img(m):
        path     = m.group(1)
        basename = os.path.basename(path)
        return f'![](images/{basename})'

    text = re.sub(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}', fix_img, text)

    # figure environment: extract caption, drop wrapper
    def fix_figure(m):
        inner = m.group(1)
        cap_m = re.search(r'\\caption\{([^}]+)\}', inner)
        caption = cap_m.group(1).strip() if cap_m else ''
        inner = re.sub(r'\\caption\{[^}]+\}', '', inner)
        inner = re.sub(r'\\label\{[^}]+\}',   '', inner)
        inner = re.sub(r'\\centering\b',       '', inner)
        inner = inner.strip()
        if not inner:
            return '\n'
        if caption:
            return f'\n{inner}\n\n*{caption}*\n'
        return f'\n{inner}\n'

    # (?:\[[^\]]*\])? matches optional [H]/[h] placement specifier
    text = re.sub(
        r'\\begin\{figure\}(?:\[[^\]]*\])?\s*(.*?)\\end\{figure\}',
        fix_figure, text, flags=re.DOTALL
    )
    return text


# ---------------------------------------------------------------------------
# Section headings
# ---------------------------------------------------------------------------

def convert_sections(text):
    text = re.sub(r'\\section\{([^}]+)\}',       lambda m: f'\n# {m.group(1)}\n',    text)
    text = re.sub(r'\\subsection\{([^}]+)\}',    lambda m: f'\n## {m.group(1)}\n',   text)
    text = re.sub(r'\\subsubsection\{([^}]+)\}', lambda m: f'\n### {m.group(1)}\n',  text)
    text = re.sub(r'\\paragraph\{([^}]+)\}',     lambda m: f'\n#### {m.group(1)}\n', text)
    return text


# ---------------------------------------------------------------------------
# Preamble / document wrapper
# ---------------------------------------------------------------------------

def strip_preamble(text):
    m = re.search(r'\\begin\{document\}', text)
    if m:
        text = text[m.end():]
    text = re.sub(r'\\end\{document\}', '', text)
    text = re.sub(r'\\maketitle\b', '', text)
    text = re.sub(r'\\newpage\b',   '\n\n---\n\n', text)
    return text


# ---------------------------------------------------------------------------
# Misc cleanup
# ---------------------------------------------------------------------------

def clean_misc(text):
    text = re.sub(r'\\(noindent|clearpage|cleardoublepage|hfill)\b', '', text)
    text = re.sub(r'\\(vspace|hspace)\{[^}]*\}', '', text)
    # Size commands: just drop the command name; leave the braces/content for Pandoc
    text = re.sub(r'\\(scriptsize|footnotesize|small|large|Large|huge|Huge)\b', '', text)
    # Don't touch \\ — it may be inside math (\begin{cases}, align rows)
    # Collapse excessive blank lines
    text = re.sub(r'\n{4,}', '\n\n\n', text)
    return text


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 3:
        print(f'Usage: {sys.argv[0]} input.tex output.md', file=sys.stderr)
        sys.exit(1)

    input_path  = sys.argv[1]
    output_path = sys.argv[2]
    base_dir    = os.path.dirname(os.path.abspath(input_path))

    text = read_file(input_path)
    text = strip_comments(text)
    text = resolve_inputs(text, base_dir)
    text = strip_preamble(text)
    text = convert_tikz(text)
    text = convert_figures(text)
    text = convert_tcolorboxes(text)
    text = convert_sections(text)
    text = clean_misc(text)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(text)

    print(f'Preprocessed → {output_path}')


if __name__ == '__main__':
    main()
