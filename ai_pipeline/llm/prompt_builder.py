"""
ai_pipeline/llm/prompt_builder.py

Builds a personalised prompt that names the user's EXACT spending reasons
so Garvis suggestions reference real habits, not generic category names.
"""

from __future__ import annotations

from typing import Dict, List, Any


LLM_PROMPT_TEMPLATE: str = """\
You are Garvis, a sharp and highly personalised personal finance advisor AI \
for an Indian user. Your suggestions MUST reference the user's actual spending \
habits by name — never give generic advice like "reduce food spending". \
Instead say: "Your Swiggy/Zomato orders appear 8+ times this month averaging \
₹320 each — cooking 4 of those meals at home could save ~₹2,500/month."

RULES (mandatory, read carefully):
1. Return ONLY valid JSON — no explanation, no markdown, no preamble.
2. The JSON must have exactly one top-level key: "suggestions" (array).
3. Each suggestion must have EXACTLY these keys (no others):
   - "action"                          (string ≤ 255 chars — name the exact service/habit)
   - "explanation"                     (string — reference actual reasons/services from the data)
   - "estimated_monthly_saving_in_inr" (number or null)
   - "confidence"                      ("high", "medium", or "low")
   - "next_step"                       (string — one concrete named action)
   - "tags"                            (array of strings)
4. Do NOT include PII, account numbers, or phone numbers.
5. Provide 2–5 suggestions.
6. Do NOT repeat suggestions the user already rejected.
7. Prioritise suggestions similar to ones the user accepted.
8. Use ₹ (Indian Rupee) for all monetary values.
9. Be specific: name the exact app (Swiggy, Netflix, Uber, Spotify, etc.),
   name the habit, quote the amount.

════════════════════════════════════════
FINANCIAL SUMMARY ({start_date} → {end_date})
════════════════════════════════════════
Total income (period):      ₹{total_income:,.0f}
Total expenses (period):    ₹{total_expense:,.0f}
Avg monthly expense:        ₹{avg_monthly_expense:,.0f}
Savings this period:        ₹{savings:,.0f}  ({savings_pct:.1f}% of income)

SPENDING BY CATEGORY:
{category_breakdown_text}

════════════════════════════════════════
EXACTLY WHAT THIS USER SPENDS ON
(reasons they personally entered — use these names in your suggestions):
════════════════════════════════════════
{reason_breakdown_text}

════════════════════════════════════════
RECENT TRANSACTIONS (with reasons):
════════════════════════════════════════
{representative_text}

════════════════════════════════════════
RECURRING / SUBSCRIPTION PATTERNS:
════════════════════════════════════════
{recurring_text}

════════════════════════════════════════
SPENDING TREND (last 3 months vs prior 3 months):
════════════════════════════════════════
{trend_text}

════════════════════════════════════════
PREVIOUS USER FEEDBACK (respect these):
════════════════════════════════════════
{feedback_text}

YOUR TASK: Generate 2–5 highly personalised, specific suggestions.
- Reference the exact service names from "EXACTLY WHAT THIS USER SPENDS ON" above
- Quote real amounts from the data
- Make next_step concrete (e.g. "Open Spotify app → Account → Cancel subscription today")
- Do NOT write anything generic

RESPOND WITH VALID JSON ONLY. NO OTHER TEXT."""


def _fmt_category_breakdown(breakdown: Dict[str, float]) -> str:
    if not breakdown:
        return "  (no expense data)"
    total = sum(breakdown.values())
    lines = []
    for cat, amt in sorted(breakdown.items(), key=lambda x: -x[1]):
        pct = (amt / total * 100) if total else 0
        lines.append(f"  {cat:<20} ₹{amt:>10,.2f}   ({pct:.1f}%)")
    return "\n".join(lines)


def _fmt_reason_breakdown(reason_breakdown: Dict[str, List[str]]) -> str:
    """Core personalization signal — category → user's own reason labels."""
    if not reason_breakdown:
        return "  (no reasons entered yet — give general advice based on categories)"
    lines = []
    for cat, reasons in sorted(reason_breakdown.items()):
        lines.append(f"  [{cat}]")
        for r in reasons:
            lines.append(f"    • {r}")
    return "\n".join(lines)


def _fmt_representative(txns: List[Dict]) -> str:
    if not txns:
        return "  (none)"
    lines = []
    for t in txns:
        reason = (t.get("reason") or "").strip()
        reason_str = f'  ← "{reason}"' if reason else ""
        lines.append(
            f"  {t['date']}  {t['category']:<16}  ₹{t['amount']:>9,.2f}{reason_str}"
        )
    return "\n".join(lines)


def _fmt_recurring(recurring: List[Dict]) -> str:
    if not recurring:
        return "  (none detected)"
    lines = []
    for r in recurring[:8]:
        cadence = r.get("cadence") or "irregular"
        lines.append(
            f"  {r['merchant']:<24}  ₹{r['average_amount']:>8,.2f}/occurrence  "
            f"cadence={cadence}  seen {r['count']}×"
        )
    return "\n".join(lines)


def _fmt_trend(trend: Dict[str, Dict]) -> str:
    if not trend:
        return "  (no trend data)"
    lines = []
    for cat, t in sorted(trend.items(), key=lambda x: -abs(x[1].get("delta_pct", 0))):
        delta = t.get("delta_pct", 0)
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
        lines.append(
            f"  {cat:<20}  prev=₹{t['prev_3m']:>8,.0f}  "
            f"last=₹{t['last_3m']:>8,.0f}  {arrow}{abs(delta):.1f}%"
        )
    return "\n".join(lines)


def trim_payload(payload: Dict) -> Dict:
    """Keep only fields the LLM needs."""
    m = payload.get("metrics", {})
    return {
        "metrics":          m,
        "reason_breakdown": payload.get("reason_breakdown", {}),
        "recurring":        payload.get("recurring", [])[:6],
        "anomalies":        payload.get("anomalies", [])[:3],
        "representative_transactions": [
            {
                "date":     t["date"],
                "amount":   t["amount"],
                "category": t["category"],
                "reason":   t.get("reason", ""),
            }
            for t in payload.get("representative_transactions", [])[:8]
        ],
    }


def build_prompt(payload: Dict, previous_feedback: List[Dict] | None = None) -> str:
    m = payload.get("metrics", {})
    total_income        = m.get("total_income", 0) or 0
    total_expense       = m.get("total_expense", 0) or 0
    avg_monthly_expense = m.get("avg_monthly_expense", 0) or 0
    savings             = total_income - total_expense
    savings_pct         = (savings / total_income * 100) if total_income else 0

    if previous_feedback:
        lines = [f'  • "{f["action"]}" → {f["feedback"]}ed by user' for f in previous_feedback]
        feedback_text = "\n".join(lines)
    else:
        feedback_text = "  None yet."

    return LLM_PROMPT_TEMPLATE.format(
        start_date=payload.get("start_date", "N/A"),
        end_date=payload.get("end_date", "N/A"),
        total_income=total_income,
        total_expense=total_expense,
        avg_monthly_expense=avg_monthly_expense,
        savings=savings,
        savings_pct=savings_pct,
        category_breakdown_text=_fmt_category_breakdown(m.get("category_breakdown", {})),
        reason_breakdown_text=_fmt_reason_breakdown(payload.get("reason_breakdown", {})),
        representative_text=_fmt_representative(
            payload.get("representative_transactions", [])
        ),
        recurring_text=_fmt_recurring(payload.get("recurring", [])),
        trend_text=_fmt_trend(m.get("trend", {})),
        feedback_text=feedback_text,
    )