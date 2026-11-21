import html
import re

ACCENT = "#0F766E"
COLOURS = {"draft": "#64748b", "edited": "#b45309", "approved": "#15803d"}
DOTS = {"draft": "⚪", "edited": "🟠", "approved": "🟢"}
STEPS = ["Consent", "Record", "Review", "Approve", "Summary"]


def badge_html(status):
    # The status comes from a fixed list, so this is safe to show as HTML
    colour = COLOURS.get(status, "#64748b")
    label = status.upper() if status in COLOURS else "UNKNOWN"
    return (
        f'<span style="background:{colour};color:white;padding:4px 12px;'
        f'border-radius:12px;font-size:0.85rem;font-weight:600;">{label}</span>'
    )


def steps_html(current):
    # current = the step in progress (0 to 4). A number past the end means every step is done.
    parts = []
    for i, name in enumerate(STEPS):
        if i < current:
            parts.append(f'<span style="color:{ACCENT};font-weight:600;">✓ {name}</span>')
        elif i == current:
            parts.append(f'<span style="background:{ACCENT};color:white;padding:3px 12px;'
                         f'border-radius:12px;font-weight:600;">{name}</span>')
        else:
            parts.append(f'<span style="color:#94a3b8;">{name}</span>')
    divider = '<span style="color:#cbd5e1;">›</span>'
    return ('<div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap;'
            'margin:2px 0 12px 0;font-size:0.95rem;">' + divider.join(parts) + "</div>")


def flag_html(reason):
    # A small amber label. The reason comes from the server, so it is escaped first.
    safe = html.escape(reason.replace(" | ", " · ")).replace("$", "&#36;")
    return ('<div style="background:#fef3c7;color:#92400e;border-left:4px solid #f59e0b;'
            'padding:4px 10px;border-radius:4px;font-size:0.85rem;margin-bottom:4px;">'
            f"<b>Check:</b> {safe}</div>")


def blur_css():
    # Optional: blurs the page behind the consent popup.
    return '<style>div[data-testid="stDialog"] { backdrop-filter: blur(6px); }</style>'


def marked_text(text, low_words):
    # Escape the text piece by piece, wrapping each low-confidence word in a wavy underline
    scores = {}
    for w in low_words:
        key = re.sub(r"[^a-z0-9]", "", w["word"].lower())
        if key:
            scores.setdefault(key, []).append(w["score"])

    out, last = [], 0
    for m in re.finditer(r"[A-Za-z0-9]+", text):
        waiting = scores.get(m.group().lower())
        if waiting:
            score = waiting.pop(0)
            out.append(html.escape(text[last:m.start()]))
            out.append(
                '<span style="text-decoration:underline wavy #dc2626;text-underline-offset:3px;" '
                f'title="Low confidence ({score:.2f})">{html.escape(m.group())}</span>'
            )
            last = m.end()
    out.append(html.escape(text[last:]))
    return "".join(out).replace("$", "&#36;")


def line_html(line_no, speaker, text, highlighted=False, low_words=None):
    # One transcript line. Everything from the server is escaped, so it can never act as HTML.
    safe_speaker = html.escape(speaker.title())
    body = marked_text(text, low_words or [])
    base = "padding:5px 10px;border-radius:6px;margin-bottom:3px;font-size:1.02rem;line-height:1.6;"
    if highlighted:
        # Dark text on yellow, so the highlight stays readable
        style = base + "background:#fde047;color:#1f2937;"
    else:
        style = base
    return f'<div style="{style}"><b>{int(line_no)}. {safe_speaker}:</b> {body}</div>'