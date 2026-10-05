"""The strategy lines: one fixed sentence in the system prompt, and each version's reason.

No decision of ours is in any of them; `nav_e2e.py`'s `-HINT*` arms append one. The second line
is sealed verbatim by `prereg-strategy.md` (its sha256 is pinned in `tests/test_nav_e2e.py`):
edit it and the registered confirmation no longer tests what it says.
"""

# The first line (2026-10-02): Sonnet's own way through H1, said in one sentence.
STRATEGY_HINT = (
    "If the request needs data gathered from many pages of a site (counting, summing, comparing "
    "or listing across pagination), do not open the pages one by one: write one browser_evaluate "
    "that fetches and parses them all and returns the result. If that finds nothing, the content "
    "is probably drawn by JavaScript: read it in the browser instead."
)
# The second line, after S5 (2026-10-02): with the first one Haiku took a single partial scroll
# as final, 0/3, where unaided it kept going when the result looked short, 3/3. "Do it in one
# call" had suppressed the check. So the extraction now has to say how much it read, and the agent
# has to hold that against the site before answering. And H1 (2026-10-02) hung for 30 minutes: a
# loop that read Next from the open page, not the fetched one, and Playwright MCP never stops an
# evaluate - so every loop gets a cap.
STRATEGY_HINT_V2 = (
    "If the request needs data gathered from many pages of a site (counting, summing, comparing "
    "or listing across pagination or infinite scroll), do not open the pages one by one: write "
    "one browser_evaluate that collects them all (fetching each page, or the data the page loads) "
    "and computes the answer in code, with a cap on every loop so it cannot run forever. Make it "
    "also return how many pages and items it read and whether more remained, and check that "
    "against what the site shows before you answer; if it fell short, fix the code and run it "
    "again. If it finds nothing, the content is probably drawn by JavaScript: read it in the "
    "browser instead."
)
# The third line, after reading why the hint sessions that walked had walked (2026-10-02): 9 of 13
# first wrote an extraction that clicked Next or set location inside the evaluate, which destroys
# the call ("Execution context was destroyed"), and then fell back to walking instead of fixing it.
STRATEGY_HINT_V3 = (
    "If the request needs data gathered from many pages of a site (counting, summing, comparing "
    "or listing across pagination or infinite scroll), do not open the pages one by one: write "
    "one browser_evaluate that collects them all and computes the answer in code, with a cap on "
    "every loop. Inside it never click or change the page's location, which destroys the call: "
    "fetch() each page's URL and parse it with DOMParser, or fetch the data the page loads; if "
    "the pages are drawn by JavaScript, find that data (a JSON request or a script on the page) "
    "first. Make it also return how many pages and items it read and whether more remained, and "
    "check that against what the site shows before you answer. If the call errors or falls "
    "short, fix the code and run it again rather than walking the pages."
)
# The fourth, after v3's only miss: on S4 run 3 the loop's cap was 10 pages on a site of 20, and
# the half it read was taken as the whole. A cap must sit far above the site, and reaching it is
# falling short.
STRATEGY_HINT_V4 = (
    "If the request needs data gathered from many pages of a site (counting, summing, comparing "
    "or listing across pagination or infinite scroll), do not open the pages one by one: write "
    "one browser_evaluate that collects them all and computes the answer in code. Give every "
    "loop a cap far above what the site could hold (a thousand pages, not ten), and treat a "
    "loop that stopped at its cap as one that fell short. Inside it never click or change the "
    "page's location, which destroys the call: fetch() each page's URL and parse it with "
    "DOMParser, or fetch the data the page loads; if the pages are drawn by JavaScript, find "
    "that data (a JSON request or a script on the page) first. Make it also return how many "
    "pages and items it read and whether more remained, and check that against what the site "
    "shows before you answer. If the call errors or falls short, fix the code and run it again "
    "rather than walking the pages."
)
# The fifth: v3's words, with only the cap clause fixed. v4 said the same and more, and was taken
# up worse (3 of 12 sessions walked, against v3's 0): a longer line is not a better one.
STRATEGY_HINT_V5 = STRATEGY_HINT_V3.replace(
    "with a cap on every loop. ",
    "with a cap on every loop far above the site's size (a loop that reaches its cap fell short). ",
)
