"""Plain-language templates for reason codes, watch-outs and recourse steps (en / ta / hi).

Numbers are inserted from computed values only; templates never contain a derived number.
"""
from __future__ import annotations


def inr(v: float) -> str:
    """Indian digit grouping, whole rupees: 123456 -> 1,23,456."""
    n = int(round(float(v)))
    neg = n < 0
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-" if neg else "") + s


def display_params(code: str, p: dict) -> dict:
    """Turn stored raw parameters into the exact strings shown in text."""
    base = code.rsplit("_", 1)[0] if code.endswith(("_POS", "_NEG")) else code
    v = p.get("value")
    d: dict[str, str] = {}
    if base in {"ACTIVE_WEEKS", "ON_TIME_BILLS", "REGULAR_SAVINGS"} and v is not None:
        d["pct"] = str(round(v * 100))
    elif base == "LONGEST_GAP" and v is not None:
        d["days"] = str(int(round(v)))
    elif base == "UNEXPLAINED_SWING" and v is not None:
        d["res_pct"] = str(round(v * 100))
        d["raw_pct"] = str(round(p.get("v_raw", 0) * 100))
    elif base == "RECOVERY_SPEED" and v is not None:
        d["weeks"] = str(max(1, int(round(v))))
    elif base == "BAD_WEEK_HEADROOM":
        d["f20"] = inr(p.get("f20", 0))
        d["e_ess"] = inr(p.get("e_ess", 0))
    elif base == "DEBT_SERVICE" and v is not None:
        d["pct"] = str(round(v * 100))
        d["emi"] = inr(p.get("emi_week", 0))
    elif base == "BOUNCED_DEBITS" and v is not None:
        d["count"] = str(int(v))
    elif base == "CASH_BUFFER" and v is not None:
        d["days"] = str(int(round(v)))
    elif base == "PLATFORM_TENURE" and v is not None:
        d["months"] = str(int(round(v)))
    elif base == "EARNINGS_PER_HOUR" and v is not None:
        d["pct"] = str(abs(round(v * 100)))
    elif code == "OVERWORK_RISK":
        d = {"weeks": str(p["weeks"]), "hours": str(p["hours"])}
    elif code == "CAPACITY_WARNING":
        d = {"f20": inr(p["f20"]), "e_ess": inr(p["e_ess"])}
    elif code.startswith("FLAG_"):
        d = {"count": str(p.get("count", 0))}
    return d


T: dict[str, dict[str, str]] = {
    # ---- consistency
    "ACTIVE_WEEKS_POS": {
        "en": "You earned in {pct}% of weeks in the last year.",
        "ta": "கடந்த ஆண்டில் {pct}% வாரங்களில் நீங்கள் வருமானம் ஈட்டியுள்ளீர்கள்.",
        "hi": "पिछले साल {pct}% हफ़्तों में आपकी कमाई हुई।"},
    "ACTIVE_WEEKS_NEG": {
        "en": "You earned in only {pct}% of weeks in the last year.",
        "ta": "கடந்த ஆண்டில் {pct}% வாரங்களில் மட்டுமே வருமானம் வந்துள்ளது.",
        "hi": "पिछले साल केवल {pct}% हफ़्तों में ही कमाई हुई।"},
    "LONGEST_GAP_POS": {
        "en": "Your longest break between earnings was {days} days.",
        "ta": "இரண்டு வருமானங்களுக்கு இடையிலான உங்கள் மிக நீண்ட இடைவெளி {days} நாட்கள்.",
        "hi": "दो कमाइयों के बीच आपका सबसे लंबा अंतर {days} दिन था।"},
    "LONGEST_GAP_NEG": {
        "en": "You had a break of {days} days with no earnings.",
        "ta": "{days} நாட்கள் எந்த வருமானமும் இல்லாத இடைவெளி இருந்தது.",
        "hi": "{days} दिन तक कोई कमाई नहीं हुई।"},
    "PAYOUT_REGULARITY_POS": {
        "en": "Your payments arrive on a regular rhythm.",
        "ta": "உங்கள் பணம் சீரான இடைவெளியில் வருகிறது.",
        "hi": "आपके भुगतान नियमित अंतराल पर आते हैं।"},
    "PAYOUT_REGULARITY_NEG": {
        "en": "The gaps between your payments vary a lot.",
        "ta": "உங்கள் பணம் வரும் இடைவெளிகள் அதிகம் மாறுபடுகின்றன.",
        "hi": "आपके भुगतानों के बीच का अंतर बहुत बदलता रहता है।"},
    # ---- stability
    "UNEXPLAINED_SWING_POS": {
        "en": "After removing predictable seasonal swings, your income varies by only {res_pct}% (before: {raw_pct}%).",
        "ta": "எதிர்பார்க்கக்கூடிய பருவகால மாற்றங்களை நீக்கிய பின், உங்கள் வருமான மாறுபாடு {res_pct}% மட்டுமே (முன்பு: {raw_pct}%).",
        "hi": "अनुमानित मौसमी उतार-चढ़ाव हटाने के बाद आपकी आय में केवल {res_pct}% बदलाव है (पहले: {raw_pct}%)।"},
    "UNEXPLAINED_SWING_NEG": {
        "en": "Even after removing seasonal swings, your income varies by {res_pct}% (before: {raw_pct}%).",
        "ta": "பருவகால மாற்றங்களை நீக்கிய பிறகும் உங்கள் வருமானம் {res_pct}% மாறுபடுகிறது (முன்பு: {raw_pct}%).",
        "hi": "मौसमी उतार-चढ़ाव हटाने के बाद भी आपकी आय में {res_pct}% बदलाव है (पहले: {raw_pct}%)।"},
    "DOWNSIDE_DEVIATION_POS": {
        "en": "Your bad weeks are not far below your usual weeks.",
        "ta": "உங்கள் மோசமான வாரங்கள் வழக்கமான வாரங்களை விட மிகவும் குறைவாக இல்லை.",
        "hi": "आपके खराब हफ़्ते आम हफ़्तों से बहुत कम नहीं होते।"},
    "DOWNSIDE_DEVIATION_NEG": {
        "en": "Some weeks fall far below your usual income.",
        "ta": "சில வாரங்களில் வருமானம் வழக்கத்தை விட மிகவும் குறைகிறது.",
        "hi": "कुछ हफ़्तों में आय आम से बहुत नीचे गिर जाती है।"},
    "RECOVERY_SPEED_POS": {
        "en": "After a bad week you usually recover within {weeks} week(s).",
        "ta": "ஒரு மோசமான வாரத்திற்குப் பிறகு பொதுவாக {weeks} வாரத்தில் மீண்டு விடுகிறீர்கள்.",
        "hi": "खराब हफ़्ते के बाद आप आम तौर पर {weeks} हफ़्ते में संभल जाते हैं।"},
    "RECOVERY_SPEED_NEG": {
        "en": "After a bad week it usually takes {weeks} weeks to recover.",
        "ta": "ஒரு மோசமான வாரத்திற்குப் பிறகு மீண்டு வர பொதுவாக {weeks} வாரங்கள் ஆகிறது.",
        "hi": "खराब हफ़्ते के बाद संभलने में आम तौर पर {weeks} हफ़्ते लगते हैं।"},
    # ---- capacity
    "BAD_WEEK_HEADROOM_POS": {
        "en": "In a bad week you still earn about ₹{f20}, and essentials take about ₹{e_ess}.",
        "ta": "மோசமான வாரத்திலும் சுமார் ₹{f20} ஈட்டுகிறீர்கள்; அத்தியாவசிய செலவுகள் சுமார் ₹{e_ess}.",
        "hi": "खराब हफ़्ते में भी आप लगभग ₹{f20} कमाते हैं, और ज़रूरी खर्च लगभग ₹{e_ess} है।"},
    "BAD_WEEK_HEADROOM_NEG": {
        "en": "In a bad week you earn about ₹{f20}, and essentials take about ₹{e_ess}, leaving little room.",
        "ta": "மோசமான வாரத்தில் சுமார் ₹{f20} ஈட்டுகிறீர்கள்; அத்தியாவசிய செலவுகள் சுமார் ₹{e_ess}, மீதம் குறைவு.",
        "hi": "खराब हफ़्ते में आप लगभग ₹{f20} कमाते हैं और ज़रूरी खर्च लगभग ₹{e_ess} है, इसलिए बचत कम रहती है।"},
    "DEBT_SERVICE_POS": {
        "en": "Existing loan repayments take {pct}% of a typical week's income.",
        "ta": "தற்போதைய கடன் தவணைகள் ஒரு சாதாரண வார வருமானத்தில் {pct}% மட்டுமே.",
        "hi": "मौजूदा कर्ज़ की किस्तें आम हफ़्ते की आय का {pct}% हैं।"},
    "DEBT_SERVICE_NEG": {
        "en": "Existing loan repayments (about ₹{emi} a week) take {pct}% of a typical week's income.",
        "ta": "தற்போதைய கடன் தவணைகள் (வாரத்திற்கு சுமார் ₹{emi}) சாதாரண வார வருமானத்தில் {pct}% எடுக்கின்றன.",
        "hi": "मौजूदा कर्ज़ की किस्तें (लगभग ₹{emi} प्रति हफ़्ता) आम हफ़्ते की आय का {pct}% ले लेती हैं।"},
    # ---- discipline
    "BOUNCED_DEBITS_POS": {
        "en": "No auto-debits bounced in the last 26 weeks.",
        "ta": "கடந்த 26 வாரங்களில் எந்த தானியங்கி பற்றும் திரும்பவில்லை.",
        "hi": "पिछले 26 हफ़्तों में कोई ऑटो-डेबिट बाउंस नहीं हुआ।"},
    "BOUNCED_DEBITS_NEG": {
        "en": "{count} auto-debit(s) bounced in the last 26 weeks.",
        "ta": "கடந்த 26 வாரங்களில் {count} தானியங்கி பற்று(கள்) திரும்பின.",
        "hi": "पिछले 26 हफ़्तों में {count} ऑटो-डेबिट बाउंस हुए।"},
    "ON_TIME_BILLS_POS": {
        "en": "{pct}% of your rent and bills were paid on time.",
        "ta": "உங்கள் வாடகை மற்றும் கட்டணங்களில் {pct}% சரியான நேரத்தில் செலுத்தப்பட்டன.",
        "hi": "आपके किराए और बिलों में से {pct}% समय पर चुकाए गए।"},
    "ON_TIME_BILLS_NEG": {
        "en": "Only {pct}% of your rent and bills were paid on time.",
        "ta": "உங்கள் வாடகை மற்றும் கட்டணங்களில் {pct}% மட்டுமே சரியான நேரத்தில் செலுத்தப்பட்டன.",
        "hi": "आपके किराए और बिलों में से केवल {pct}% समय पर चुकाए गए।"},
    "CASH_BUFFER_POS": {
        "en": "Your account usually holds about {days} days of expenses.",
        "ta": "உங்கள் கணக்கில் பொதுவாக சுமார் {days} நாட்களுக்கான செலவுத் தொகை இருக்கிறது.",
        "hi": "आपके खाते में आम तौर पर लगभग {days} दिन के खर्च जितना पैसा रहता है।"},
    "CASH_BUFFER_NEG": {
        "en": "Your account usually holds only about {days} days of expenses.",
        "ta": "உங்கள் கணக்கில் பொதுவாக சுமார் {days} நாட்களுக்கான செலவுத் தொகை மட்டுமே இருக்கிறது.",
        "hi": "आपके खाते में आम तौर पर केवल लगभग {days} दिन के खर्च जितना पैसा रहता है।"},
    "REGULAR_SAVINGS_POS": {
        "en": "You saved something in {pct}% of recent months.",
        "ta": "சமீபத்திய மாதங்களில் {pct}% மாதங்களில் சேமித்துள்ளீர்கள்.",
        "hi": "हाल के {pct}% महीनों में आपने कुछ बचत की।"},
    "REGULAR_SAVINGS_NEG": {
        "en": "Regular savings were seen in only {pct}% of recent months.",
        "ta": "சமீபத்திய மாதங்களில் {pct}% மாதங்களில் மட்டுமே சேமிப்பு காணப்பட்டது.",
        "hi": "हाल के केवल {pct}% महीनों में नियमित बचत दिखी।"},
    "DEBT_SERVICE_NONE": {
        "en": "No existing loan repayments were found in your statements.",
        "ta": "உங்கள் அறிக்கைகளில் தற்போதைய கடன் தவணைகள் எதுவும் காணப்படவில்லை.",
        "hi": "आपके स्टेटमेंट में कोई मौजूदा कर्ज़ की किस्त नहीं मिली।"},
    "REGULAR_SAVINGS_NONE": {
        "en": "No regular savings were seen in recent months.",
        "ta": "சமீபத்திய மாதங்களில் வழக்கமான சேமிப்பு எதுவும் காணப்படவில்லை.",
        "hi": "हाल के महीनों में कोई नियमित बचत नहीं दिखी।"},
    "CASH_BUFFER_NONE": {
        "en": "Your account balance usually runs close to zero, leaving no cushion for a bad week.",
        "ta": "உங்கள் கணக்கு இருப்பு பொதுவாக பூஜ்ஜியத்திற்கு அருகில் உள்ளது; மோசமான வாரத்திற்கு கையிருப்பு இல்லை.",
        "hi": "आपके खाते का बैलेंस आम तौर पर शून्य के आसपास रहता है, इसलिए खराब हफ़्ते के लिए कोई बचत नहीं रहती।"},
    # ---- resilience
    "INCOME_CONCENTRATION_POS": {
        "en": "Your income comes from more than one source.",
        "ta": "உங்கள் வருமானம் ஒன்றுக்கு மேற்பட்ட மூலங்களிலிருந்து வருகிறது.",
        "hi": "आपकी आय एक से ज़्यादा स्रोतों से आती है।"},
    "INCOME_CONCENTRATION_NEG": {
        "en": "Almost all of your income comes from one source.",
        "ta": "உங்கள் வருமானம் கிட்டத்தட்ட முழுவதும் ஒரே மூலத்திலிருந்து வருகிறது.",
        "hi": "आपकी लगभग सारी आय एक ही स्रोत से आती है।"},
    "PLATFORM_TENURE_POS": {
        "en": "You have earned from your main sources for about {months} months.",
        "ta": "உங்கள் முக்கிய வருமான மூலங்களிலிருந்து சுமார் {months} மாதங்களாக ஈட்டி வருகிறீர்கள்.",
        "hi": "आप अपने मुख्य स्रोतों से लगभग {months} महीनों से कमा रहे हैं।"},
    "PLATFORM_TENURE_NEG": {
        "en": "Your main income sources are recent (about {months} months).",
        "ta": "உங்கள் முக்கிய வருமான மூலங்கள் புதியவை (சுமார் {months} மாதங்கள்).",
        "hi": "आपके मुख्य आय स्रोत नए हैं (लगभग {months} महीने)।"},
    "EARNINGS_PER_HOUR_POS": {
        "en": "Your earnings per active hour are rising (about {pct}% per quarter).",
        "ta": "ஒரு செயலில் உள்ள மணிநேரத்திற்கான உங்கள் வருமானம் உயர்ந்து வருகிறது (காலாண்டுக்கு சுமார் {pct}%).",
        "hi": "प्रति सक्रिय घंटे आपकी कमाई बढ़ रही है (हर तिमाही लगभग {pct}%)।"},
    "EARNINGS_PER_HOUR_NEG": {
        "en": "Your earnings per active hour are falling (about {pct}% per quarter).",
        "ta": "ஒரு செயலில் உள்ள மணிநேரத்திற்கான உங்கள் வருமானம் குறைந்து வருகிறது (காலாண்டுக்கு சுமார் {pct}%).",
        "hi": "प्रति सक्रिय घंटे आपकी कमाई घट रही है (हर तिमाही लगभग {pct}%)।"},
    # ---- watch-outs
    "OVERWORK_RISK": {
        "en": "You worked more than {hours} hours in {weeks} of the last 26 weeks. Very long hours are a health risk and do not raise your score.",
        "ta": "கடந்த 26 வாரங்களில் {weeks} வாரங்களில் {hours} மணிநேரத்திற்கு மேல் வேலை செய்துள்ளீர்கள். மிக நீண்ட வேலை நேரம் உடல்நலத்திற்கு ஆபத்து; அது உங்கள் மதிப்பெண்ணை உயர்த்தாது.",
        "hi": "पिछले 26 में से {weeks} हफ़्तों में आपने {hours} घंटे से ज़्यादा काम किया। बहुत लंबे घंटे सेहत के लिए जोखिम हैं और इनसे आपका स्कोर नहीं बढ़ता।"},
    "CAPACITY_WARNING": {
        "en": "In a bad week (about ₹{f20}) your essentials (about ₹{e_ess}) use up all your income, so no new weekly repayment is safe right now.",
        "ta": "மோசமான வாரத்தில் (சுமார் ₹{f20}) உங்கள் அத்தியாவசிய செலவுகள் (சுமார் ₹{e_ess}) முழு வருமானத்தையும் எடுத்துக்கொள்கின்றன; எனவே இப்போது புதிய வாராந்திர தவணை பாதுகாப்பானது அல்ல.",
        "hi": "खराब हफ़्ते में (लगभग ₹{f20}) आपके ज़रूरी खर्च (लगभग ₹{e_ess}) पूरी आय ले लेते हैं, इसलिए अभी कोई नई साप्ताहिक किस्त सुरक्षित नहीं है।"},
    "FLAG_ROUND_TRIP": {
        "en": "{count} credit(s) mirror transfers from your own accounts. They are not counted as income and a credit officer will review them.",
        "ta": "{count} வரவு(கள்) உங்கள் சொந்த கணக்குகளிலிருந்து வந்த பரிமாற்றங்களைப் போல உள்ளன. அவை வருமானமாகக் கணக்கிடப்படவில்லை; கடன் அலுவலர் அவற்றைச் சரிபார்ப்பார்.",
        "hi": "{count} जमा आपके अपने खातों से हुए ट्रांसफ़र जैसे हैं। इन्हें आय नहीं गिना गया है और क्रेडिट अधिकारी इनकी जाँच करेंगे।"},
    "FLAG_UNMATCHED_PAYOUT": {
        "en": "{count} platform payout(s) have no matching bank credit. Add the bank account they were paid into so they can be counted.",
        "ta": "{count} தள பணவரவு(கள்) எந்த வங்கி வரவுடனும் பொருந்தவில்லை. அவை கணக்கிடப்பட, பணம் வந்த வங்கிக் கணக்கைச் சேர்க்கவும்.",
        "hi": "{count} प्लेटफ़ॉर्म भुगतान किसी बैंक जमा से मेल नहीं खाते। इन्हें गिनने के लिए वह बैंक खाता जोड़ें जिसमें पैसा आया था।"},
    "FLAG_UNEXPLAINED_LARGE_CREDIT": {
        "en": "{count} large one-off credit(s) could not be explained as earnings and are not counted.",
        "ta": "{count} பெரிய ஒருமுறை வரவு(கள்) வருமானமாக விளக்க முடியவில்லை; அவை கணக்கிடப்படவில்லை.",
        "hi": "{count} बड़े एक-बार के जमा को कमाई के रूप में समझाया नहीं जा सका, इसलिए उन्हें नहीं गिना गया।"},
    "FLAG_LARGE_RECENT_CREDIT": {
        "en": "{count} unusually large credit(s) arrived in the 14 days before this report. A credit officer will review them.",
        "ta": "இந்த அறிக்கைக்கு முந்தைய 14 நாட்களில் {count} அசாதாரணமாக பெரிய வரவு(கள்) வந்துள்ளன. கடன் அலுவலர் அவற்றைச் சரிபார்ப்பார்.",
        "hi": "इस रिपोर्ट से पहले के 14 दिनों में {count} असामान्य रूप से बड़े जमा आए। क्रेडिट अधिकारी इनकी जाँच करेंगे।"},
    # ---- recourse fragments and sentence
    "STEP_buffer_days": {
        "en": "keep at least {to} days of expenses in your account for 8 weeks",
        "ta": "8 வாரங்களுக்கு உங்கள் கணக்கில் குறைந்தது {to} நாட்களுக்கான செலவுத் தொகையை வைத்திருங்கள்",
        "hi": "8 हफ़्तों तक अपने खाते में कम से कम {to} दिन के खर्च जितना पैसा रखें"},
    "STEP_on_time_rate": {
        "en": "pay at least {to}% of your rent and bills on time for 6 months",
        "ta": "6 மாதங்களுக்கு உங்கள் வாடகை மற்றும் கட்டணங்களில் குறைந்தது {to}% சரியான நேரத்தில் செலுத்துங்கள்",
        "hi": "6 महीनों तक अपने किराए और बिलों में से कम से कम {to}% समय पर चुकाएँ"},
    "STEP_bounces": {
        "en": "avoid any bounced auto-debit for 26 weeks",
        "ta": "26 வாரங்களுக்கு எந்த தானியங்கி பற்றும் திரும்பாமல் பார்த்துக்கொள்ளுங்கள்",
        "hi": "26 हफ़्तों तक कोई ऑटो-डेबिट बाउंस न होने दें"},
    "STEP_active_week_share": {
        "en": "earn in at least {to}% of weeks over the next year",
        "ta": "அடுத்த ஆண்டில் குறைந்தது {to}% வாரங்களில் வருமானம் ஈட்டுங்கள்",
        "hi": "अगले साल कम से कम {to}% हफ़्तों में कमाई करें"},
    "STEP_SENTENCE": {
        "en": "{actions} to move from Band {from_band} to Band {to_band}.",
        "ta": "{actions} — இதனால் நீங்கள் {from_band} பிரிவிலிருந்து {to_band} பிரிவுக்கு முன்னேறலாம்.",
        "hi": "{actions} — इससे आप बैंड {from_band} से बैंड {to_band} में जा सकते हैं।"},
    "AND": {"en": " and ", "ta": " மற்றும் ", "hi": " और "},
    # ---- data sufficiency
    "NEED_MONTHS": {
        "en": "Not enough data yet — add: older bank statements so we can see at least 12 months (we have {months}).",
        "ta": "இன்னும் போதுமான தரவு இல்லை — சேர்க்கவும்: குறைந்தது 12 மாதங்களைக் காண பழைய வங்கி அறிக்கைகள் (இப்போது {months}).",
        "hi": "अभी पर्याप्त डेटा नहीं है — जोड़ें: पुराने बैंक स्टेटमेंट ताकि कम से कम 12 महीने दिखें (अभी {months})।"},
    "NEED_SOURCES": {
        "en": "Not enough data yet — add: another bank account or a platform payout statement.",
        "ta": "இன்னும் போதுமான தரவு இல்லை — சேர்க்கவும்: மற்றொரு வங்கிக் கணக்கு அல்லது தள பணவரவு அறிக்கை.",
        "hi": "अभी पर्याप्त डेटा नहीं है — जोड़ें: एक और बैंक खाता या प्लेटफ़ॉर्म भुगतान स्टेटमेंट।"},
    "NEED_RECONCILE": {
        "en": "Not enough data yet — add: your platform payout statement so payouts can be matched to bank credits.",
        "ta": "இன்னும் போதுமான தரவு இல்லை — சேர்க்கவும்: பணவரவுகளை வங்கி வரவுகளுடன் பொருத்த உங்கள் தள பணவரவு அறிக்கை.",
        "hi": "अभी पर्याप्त डेटा नहीं है — जोड़ें: अपना प्लेटफ़ॉर्म भुगतान स्टेटमेंट ताकि भुगतानों का बैंक जमा से मिलान हो सके।"},
}


def render(code: str, params: dict, lang: str = "en") -> str:
    tpl = T.get(code, {}).get(lang) or T.get(code, {}).get("en") or code
    try:
        return tpl.format(**params)
    except (KeyError, IndexError):
        return T.get(code, {}).get("en", code).format_map(_Safe(params))


class _Safe(dict):
    def __missing__(self, key):
        return ""
