import gradio as gr
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json
import re

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TaptwiceAEOBot/1.0)"}

AI_CRAWLERS = [
    "GPTBot", "ChatGPT-User", "ClaudeBot", "Claude-Web",
    "PerplexityBot", "Google-Extended", "Googlebot-Extended",
    "Bytespider", "CCBot", "anthropic-ai", "cohere-ai"
]

def fetch(url, timeout=10):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        return r.text, r.status_code
    except Exception as e:
        return None, str(e)

def score_bar(score, total):
    pct = int((score / total) * 100)
    filled = pct // 5
    bar = "█" * filled + "░" * (20 - filled)
    return f"[{bar}] {pct}%"

def audit(url):
    if not url.startswith("http"):
        url = "https://" + url

    results = []
    score = 0
    max_score = 0

    results.append(f"## AEO & GEO Audit Report")
    results.append(f"**URL:** {url}\n")

    # ── 1. Fetch main page ──────────────────────────────────────────────
    html, status = fetch(url)
    if not html:
        return f"Could not fetch {url}: {status}"

    soup = BeautifulSoup(html, "html.parser")
    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"

    results.append("---")
    results.append("### 1. On-Page Signals\n")

    # Title
    max_score += 10
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""
    if title:
        tlen = len(title)
        if 40 <= tlen <= 65:
            results.append(f"✅ **Meta Title** ({tlen} chars): `{title}`")
            score += 10
        elif tlen > 0:
            results.append(f"⚠️ **Meta Title** ({tlen} chars — ideal: 40–65): `{title}`")
            score += 5
    else:
        results.append("❌ **Meta Title**: Missing")

    # Meta description
    max_score += 10
    desc_tag = soup.find("meta", attrs={"name": re.compile("description", re.I)})
    desc = desc_tag.get("content", "").strip() if desc_tag else ""
    if desc:
        dlen = len(desc)
        is_question = any(desc.strip().startswith(q) for q in ["What", "How", "Why", "Who", "Which", "When", "Is ", "Are ", "Can ", "Does "]) or "?" in desc
        if 120 <= dlen <= 160:
            results.append(f"✅ **Meta Description** ({dlen} chars{'  — question-format' if is_question else ''}): `{desc[:100]}...`")
            score += 10
        else:
            results.append(f"⚠️ **Meta Description** ({dlen} chars — ideal: 120–160): `{desc[:100]}...`")
            score += 5
    else:
        results.append("❌ **Meta Description**: Missing")

    # Meta keywords
    max_score += 5
    kw_tag = soup.find("meta", attrs={"name": re.compile("keywords", re.I)})
    kw = kw_tag.get("content", "").strip() if kw_tag else ""
    if kw:
        results.append(f"✅ **Meta Keywords**: `{kw[:80]}`")
        score += 5
    else:
        results.append("⚠️ **Meta Keywords**: Not set (minor for AEO, still good practice)")
        score += 2

    # H1
    max_score += 10
    h1s = [h.get_text(strip=True) for h in soup.find_all("h1")]
    if len(h1s) == 1:
        results.append(f"✅ **H1**: `{h1s[0][:80]}`")
        score += 10
    elif len(h1s) > 1:
        results.append(f"⚠️ **H1**: Multiple H1s found ({len(h1s)}) — consolidate to one")
        score += 4
    else:
        results.append("❌ **H1**: Missing")

    # Canonical
    max_score += 5
    canon = soup.find("link", attrs={"rel": "canonical"})
    if canon and canon.get("href"):
        results.append(f"✅ **Canonical**: `{canon['href']}`")
        score += 5
    else:
        results.append("❌ **Canonical**: Missing")

    # Open Graph
    max_score += 5
    og_title = soup.find("meta", property="og:title")
    og_desc = soup.find("meta", property="og:description")
    if og_title and og_desc:
        results.append(f"✅ **Open Graph**: Title + Description present")
        score += 5
    elif og_title or og_desc:
        results.append(f"⚠️ **Open Graph**: Partial (add both og:title and og:description)")
        score += 2
    else:
        results.append("❌ **Open Graph**: Missing")

    # JSON-LD structured data
    max_score += 15
    ld_scripts = soup.find_all("script", type="application/ld+json")
    ld_types = []
    faq_found = False
    for s in ld_scripts:
        try:
            d = json.loads(s.string or "{}")
            t = d.get("@type", "")
            if isinstance(t, list):
                ld_types.extend(t)
            elif t:
                ld_types.append(t)
            if t == "FAQPage" or (isinstance(t, list) and "FAQPage" in t):
                faq_found = True
        except:
            pass
    if ld_types:
        results.append(f"✅ **Structured Data (JSON-LD)**: {', '.join(ld_types)}")
        score += 10
        if faq_found:
            results.append(f"  ✅ **FAQPage schema** detected — strong AEO signal")
            score += 5
    else:
        results.append("❌ **Structured Data**: No JSON-LD found — add FAQPage, Organization, or Article schema")

    # ── 2. robots.txt ──────────────────────────────────────────────────
    results.append("\n---")
    results.append("### 2. robots.txt — AI Crawler Access\n")
    max_score += 15

    robots_url = urljoin(base, "/robots.txt")
    robots_text, robots_status = fetch(robots_url)

    if robots_text and isinstance(robots_status, int) and robots_status == 200:
        blocked = []
        allowed = []
        for crawler in AI_CRAWLERS:
            pattern = re.compile(
                rf"User-agent:\s*{re.escape(crawler)}.*?(?=User-agent:|$)",
                re.IGNORECASE | re.DOTALL
            )
            match = pattern.search(robots_text)
            if match:
                block = re.search(r"Disallow:\s*/", match.group(), re.IGNORECASE)
                if block:
                    blocked.append(crawler)
                else:
                    allowed.append(crawler)

        if blocked:
            results.append(f"⚠️ **AI crawlers blocked**: {', '.join(blocked)}")
            results.append("  → These engines cannot index your site for AI answers")
            score += 5
        else:
            results.append(f"✅ **AI crawlers**: All allowed (no blocks found)")
            score += 15

        # Check for wildcard Disallow
        if re.search(r"User-agent:\s*\*\s*\nDisallow:\s*/\s*$", robots_text, re.IGNORECASE | re.MULTILINE):
            results.append("❌ **Wildcard block**: `Disallow: /` for all bots — blocks everything including AI")
            score -= 10
    else:
        results.append(f"⚠️ **robots.txt**: Not found or unreachable ({robots_url})")
        score += 5

    # ── 3. llms.txt ─────────────────────────────────────────────────────
    results.append("\n---")
    results.append("### 3. llms.txt — AI Context File\n")
    max_score += 20

    llms_url = urljoin(base, "/llms.txt")
    llms_text, llms_status = fetch(llms_url)

    if llms_text and isinstance(llms_status, int) and llms_status == 200:
        lines = [l.strip() for l in llms_text.splitlines() if l.strip()]
        results.append(f"✅ **llms.txt found** ({len(lines)} lines)")
        score += 20
        has_h1 = any(l.startswith("# ") for l in lines)
        has_desc = any(l.startswith("> ") for l in lines)
        has_links = any(l.startswith("- ") or l.startswith("## ") for l in lines)
        if has_h1:
            results.append("  ✅ Has brand name heading")
        else:
            results.append("  ⚠️ Missing `# BrandName` heading")
        if has_desc:
            results.append("  ✅ Has brand description block")
        else:
            results.append("  ⚠️ Missing `> description` block")
        if has_links:
            results.append("  ✅ Has linked sections")
        else:
            results.append("  ⚠️ No section links — add ## sections with page links")
    else:
        results.append(f"❌ **llms.txt**: Not found at `{llms_url}`")
        results.append("  → This file tells AI engines what your brand is about. Add it.")
        results.append("  → Format: `# BrandName` → `> Description` → `## Sections` with links")

    # ── 4. AEO Content Signals ───────────────────────────────────────────
    results.append("\n---")
    results.append("### 4. AEO Content Signals\n")
    max_score += 10

    text = soup.get_text(" ", strip=True)
    question_words = ["what is", "how to", "why does", "who is", "which is", "when should", "can i", "does it"]
    q_count = sum(1 for q in question_words if q in text.lower())

    if q_count >= 3:
        results.append(f"✅ **Question-based content**: {q_count} question patterns found — good for AEO")
        score += 10
    elif q_count > 0:
        results.append(f"⚠️ **Question-based content**: Only {q_count} question patterns — add more FAQ-style content")
        score += 4
    else:
        results.append("❌ **Question-based content**: No question patterns detected — add FAQ sections")

    word_count = len(text.split())
    results.append(f"ℹ️ **Page word count**: ~{word_count:,} words")

    # ── Final Score ──────────────────────────────────────────────────────
    results.append("\n---")
    results.append("### AEO Readiness Score\n")
    pct = int((score / max_score) * 100)
    bar = score_bar(score, max_score)

    if pct >= 75:
        grade = "🟢 Strong"
    elif pct >= 50:
        grade = "🟡 Moderate"
    elif pct >= 30:
        grade = "🟠 Weak"
    else:
        grade = "🔴 Poor"

    results.append(f"**{grade}** {bar}")
    results.append(f"\nScore: **{score}/{max_score}** ({pct}%)\n")

    results.append("---")
    results.append("*Audit by [Taptwice Media](https://taptwicemedia.com) — AEO & GEO specialists*")

    return "\n".join(results)


demo = gr.Interface(
    fn=audit,
    inputs=gr.Textbox(
        label="Enter website URL",
        placeholder="https://yourwebsite.com",
        scale=4
    ),
    outputs=gr.Markdown(label="AEO Audit Report"),
    title="AEO Readiness Auditor by Taptwice Media",
    description=(
        "Instantly audit any website for Answer Engine Optimization (AEO) and Generative Engine Optimization (GEO) readiness. "
        "Checks meta signals, robots.txt AI crawler access, llms.txt, structured data, and content patterns. "
        "Built by [Taptwice Media](https://taptwicemedia.com) — the AEO & GEO specialists."
    ),
    examples=[
        ["https://taptwicemedia.com"],
        ["https://perplexity.ai"],
        ["https://hubspot.com"],
    ],
    flagging_mode="never",
)

if __name__ == "__main__":
    demo.launch(theme=gr.themes.Soft())
