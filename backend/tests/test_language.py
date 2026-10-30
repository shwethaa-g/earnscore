from app.i18n.templates import T, inr, render
from app.services import language


class FakeLLM(language.LanguageProvider):
    name = "fake"

    def __init__(self, mode):
        self.mode = mode

    def rewrite(self, text, lang):
        if self.mode == "change_number":
            return text.replace("88", "98")
        if self.mode == "add_number":
            return text + " You could earn 5000 more."
        return "Good news: " + text

    def tag(self, narration):
        return "earned"


def test_numbers_post_check():
    assert language.numbers_match("You earned in 88% of weeks.", "Great - 88% of weeks had income.")
    assert not language.numbers_match("You earned in 88% of weeks.", "You earned in 98% of weeks.")
    assert language.numbers_match("₹1,20,000", "₹120000")
    assert language.numbers_match("88%", "८८%")  # Devanagari digits are compared by value


def test_llm_cannot_change_numbers():
    params = {"value": 0.88}
    try:
        language.set_provider(FakeLLM("change_number"))
        out = language.explain("ACTIVE_WEEKS_POS", params, "en")
        assert out["source"] == "template" and "88%" in out["text"]
        language.set_provider(FakeLLM("add_number"))
        assert language.explain("ACTIVE_WEEKS_POS", params, "en")["source"] == "template"
        language.set_provider(FakeLLM("ok"))
        out = language.explain("ACTIVE_WEEKS_POS", params, "en")
        assert out["source"] == "fake" and out["text"].startswith("Good news")
    finally:
        language.set_provider(None)


def test_llm_never_changes_score():
    from tests.test_scoring import make_input
    from app.scoring import engine

    inp = make_input([4000 if i % 5 else 0 for i in range(52)])
    before = engine.run(inp)
    language.set_provider(FakeLLM("change_number"))
    try:
        texts = [language.explain(r["code"], r["params"], "en") for r in before["reasons"]]
        after = engine.run(inp)
    finally:
        language.set_provider(None)
    assert before["score"] == after["score"] and before["band"] == after["band"]
    from app.i18n.templates import display_params
    for r, t in zip(before["reasons"], texts):
        template = render(r["code"], display_params(r["code"], r["params"]), "en")
        assert language.numbers_match(template, t["text"])


def test_all_templates_have_three_languages():
    for code, langs in T.items():
        assert set(langs) == {"en", "ta", "hi"}, code


def test_inr_grouping_and_render():
    assert inr(1234567) == "12,34,567" and inr(999) == "999"
    assert "₹4,500" in render("BAD_WEEK_HEADROOM_POS", {"f20": "4,500", "e_ess": "2,000"}, "en")
