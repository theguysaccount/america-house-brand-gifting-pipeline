"""Read one public web page and decide, from its own words, whether it is a brand's creator,
ambassador, affiliate or gifting application page, and how a person applies.

Pure functions over HTML text: no network, no state. Everything published about a listing comes
from here, so every rule is conservative. A page is listed only when its address or headline names
the program AND the page shows a way to apply. Wholesale, stockist, careers, catalogue and
donation pages are never listed.
"""
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .common import site_key

# ------------------------------------------------------------------------------------------------
# Vocabulary
# ------------------------------------------------------------------------------------------------
TYPES = [
    # (key, label, pattern for addresses/headlines, pattern for running text)
    ("ambassador", "Ambassador program",
     r"ambassad(?:or|ors|eur|eurs|rice|ress)|botschafter|embajador|embaixador|ambasciator|brand[\s_-]*rep(?:s|resentative)?\b|street[\s_-]*team|rep[\s_-]*(?:team|program|search)",
     r"\b(?:brand\s+)?ambassadors?\b|\bbrand\s+reps?\b|\bstreet\s+team\b"),
    ("affiliate", "Affiliate program",
     r"affiliat|afiliad|partnerprogramm",
     r"\baffiliates?\b|\baffiliate\s+(?:program|partner|link|commission)"),
    ("creator", "Creator and influencer program",
     r"influenc|creators?\b|\bugc\b|\bkol\b|blogger",
     r"\binfluencers?\b|\bcontent\s+creators?\b|\bcreator\s+(?:program|community|collective|club|team)\b|\bugc\b|\bmicro[\s-]?influencers?\b"),
    ("gifting", "PR and gifting",
     r"\bpr[\s_-]+(?:list|package|packages|box|boxes|mailer|request|requests|inquir\w+|partnerships?)|gifted|product[\s_-]+seeding|\bseeding\b|pr[\s_-]*(?:&|and)[\s_-]*(?:collab|influenc|partner)\w*",
     r"\bpr\s+(?:list|packages?|box(?:es)?|mailers?|requests?)\b|\bgifted\s+(?:collab\w*|products?|partnerships?)\b|\bproduct\s+seeding\b|\bfree\s+products?\s+in\s+exchange\b"),
    ("collab", "Collaborations",
     r"collab|partner[\s_-]*with[\s_-]*us|work[\s_-]*with[\s_-]*us|brand[\s_-]*partnerships?",
     r"\bcollab(?:s|orations?|orate)?\b|\bpartner\s+with\s+us\b|\bwork\s+with\s+us\b"),
]
TYPE_LABEL = {k: label for k, label, _, _ in TYPES}
TYPE_ORDER = [k for k, _, _, _ in TYPES]

# Words that show a collaboration or partnership page is about social creators, not other businesses.
CREATOR_CONTEXT = re.compile(
    r"\binfluencers?\b|\bcontent\s+creat(?:or|ors|ion)\b|\bcreators?\b|\bugc\b|\bfollowers\b|\binstagram\b|\btik\s?tok\b|"
    r"\byoutube\b|\bsocial\s+media\b|\bambassadors?\b|\baffiliates?\b|\bbloggers?\b|\bpodcast(?:er|ers)?\b", re.I)

APPLY_WORDS = re.compile(
    r"\bappl(?:y|ying)\b|\bapplications?\b|\bsign\s*up\b|\bjoin\s+(?:us|our|the|now|today)\b|\bbecome\s+an?\b|\bregister\b|"
    r"\bfill\s+(?:out|in)\b|\bget\s+in\s+touch\b|\breach\s+out\b|\bsubmit\b|\bcontact\s+us\b|\benquire\b|\binquire\b|"
    r"\bbewerben\b|\banmelden\b|\bpostuler\b|\binscri", re.I)

# Pages aimed at other businesses or other purposes. Checked against the address and the headline.
COMMERCIAL = re.compile(
    r"wholesal|stockist|retailer|reseller|distribut|\bb2b\b|trade[\s_-]*(?:account|program|partner)|for[\s_-]*professionals|"
    r"salon|franchise|private[\s_-]*label|white[\s_-]*label|co[\s_-]*pack|manufactur|supplier|vendor|corporate[\s_-]*gift|"
    r"bulk[\s_-]*order|fundrais|careers?\b|\bjobs?\b|hiring|employment|donat|charit|grant\b|scholarship|our[\s_-]*partners|"
    r"delivery[\s_-]*partner|store[\s_-]*locator|where[\s_-]*to[\s_-]*buy|loyalty|rewards?\b|refer[\s_-]*a[\s_-]*friend|"
    r"referral[\s_-]*program|subscription|gift[\s_-]*cards?", re.I)
CREATOR_HEADLINE = re.compile(r"ambassad|affiliat|influenc|creators?\b|\bugc\b|collab|\bpr[\s_-]+(?:list|package|request)|gifted", re.I)

CLOSED = re.compile(
    r"\b(?:not|no\s+longer)\s+(?:currently\s+)?(?:accepting|taking|reviewing)\s+(?:any\s+)?(?:new\s+)?(?:applications?|ambassadors?|affiliates?|"
    r"collaborations?|requests?|submissions?|partners?|creators?|influencers?)\b|\bapplications?\s+(?:are|is)\s+(?:now\s+|currently\s+)?"
    r"(?:closed|paused|on\s+hold|full)\b|\b(?:program|programme)\s+is\s+(?:now\s+|currently\s+)?(?:closed|paused|full|on\s+hold)\b|"
    r"\bwe(?:'|’)?re\s+(?:currently\s+)?(?:at\s+capacity|not\s+onboarding)\b", re.I)

# Stores this directory does not list: age-restricted goods, and "programs" that charge people to join.
RESTRICTED = re.compile(
    r"\b(?:cbd|thc|cannabis|marijuana|hemp|vape|vaping|e-?cig\w*|tobacco|nicotine|cigars?|hookah|firearms?|ammunition|"
    r"ammo|rifles?|vodka|whisk(?:e)?y|tequila|bourbon|\bgin\b|\brum\b|beer|brewery|wine|winery|liquor|distillery|spirits|"
    r"hard\s+seltzer|alcohol(?:ic)?|erotic|adult\s+toys?|sex\s+toys?|delta[\s-]?[89]|kratom|psilocybin|kava|"
    r"casino|betting|sportsbook)\b", re.I)
RESTRICTED_SAFE = re.compile(
    r"non[\s-]?alcoholic|alcohol[\s-]?free|no\s+alcohol|zero[\s-]?proof|0(?:\.0)?\s?%\s*(?:abv|alcohol)|root\s+beer|ginger\s+beer|"
    r"butter\s*beer|wine\s+gums?|rum\s+(?:cake|raisin)|spirits?\s+of\s+|team\s+spirit|free\s+spirits?|kindred\s+spirits?|"
    r"mocktails?|beer\s+(?:bread|batter|nuts|cheese)|wine\s+(?:vinegar|pairing)", re.I)
# A store-wide age gate for 21+ goods. (Many themes carry an unused "are you 18?" pop-up in their markup,
# and many programs simply require adult applicants, so those phrases are not treated as a gate.)
AGE_GATE = re.compile(r"\bare\s+you\s+(?:over\s+)?21\b|\b21\s+(?:years?\s+old\s+)?or\s+older\s+to\s+enter\b|"
                      r"\bmust\s+be\s+(?:at\s+least\s+|over\s+)?21\s+(?:years?\s+old\s+)?to\s+(?:enter|view|visit)\b|"
                      r"\bof\s+legal\s+(?:drinking|smoking)\s+age\b", re.I)
# Explicit charges for joining. Welcome kits and "no joining fee" are common and fine, so a price or a
# plain statement that payment is required must be present, and negations are skipped.
PAY_TO_JOIN = re.compile(
    r"\b(?:starter|ambassador|business|launch|enrol+ment)\s+(?:kit|pack(?:age)?)\s*[-–:]?\s*[$£€₹]\s?\d|"
    r"[$£€₹]\s?\d[\d,.]*\s+(?:starter|ambassador|joining|membership|enrol+ment|sign[\s-]?up)\s+(?:kit|fee|pack(?:age)?)\b|"
    r"\b(?:joining|membership|enrol+ment|registration|listing|sign[\s-]?up)\s+fee\s*(?:of|is|:)\s*[$£€₹]?\s?\d|"
    r"\bpay\s+(?:your\s+|the\s+|a\s+)?(?:listing|joining|membership|enrol+ment|registration)\s+fee\b|"
    r"\bpay\s+[$£€₹]\s?\d[\d,.]*\s+(?:now|to\s+join|upfront)\b|"
    r"\bone[\s-]time\s+(?:fee|payment)\s*(?:of|:)\s*[$£€₹]\s?\d|"
    r"\b(?:purchase|buy)\s+(?:the|a|an|your)\s+[\w\s]{0,24}(?:kit|pack(?:age)?)\s+to\s+(?:join|become|start|qualify)\b|"
    r"\bdownline\b|\bupline\b|\bcompensation\s+plan\b|\bmulti[\s-]?level\b", re.I)
_NEGATED = re.compile(r"\b(?:no|not|without|zero|free|never|isn(?:'|’)?t|aren(?:'|’)?t|don(?:'|’)?t)\b[^.!?]{0,30}$", re.I)


def pay_to_join(text):
    for m in PAY_TO_JOIN.finditer(text):
        if not _NEGATED.search(text[max(0, m.start() - 40):m.start()]):
            return True
    return False


def restricted(*texts):
    """True when a brand's own name, address or description points at age-restricted goods."""
    blob = RESTRICTED_SAFE.sub(" ", " ".join(t for t in texts if t))
    return bool(RESTRICTED.search(blob))


CHALLENGE_TITLE = re.compile(r"captcha|verify\s+you\s+are\s+(?:a\s+)?human|are\s+you\s+a\s+robot|access\s+denied|just\s+a\s+moment|"
                             r"attention\s+required|security\s+check|request\s+blocked|pardon\s+our\s+interruption|bot\s+verification", re.I)
CHALLENGE_BODY = ("cf-chl-", "challenge-platform", "/cdn-cgi/challenge", "px-captcha", "captcha-delivery.com",
                  "_incapsula_resource", "checking your browser before", "enable javascript and cookies to continue")

# Creator and affiliate platforms a brand can send applicants to. (key, label, host suffixes)
PLATFORMS = [
    ("shopify_collabs", "Shopify Collabs", ["collabs.shopify.com"]),
    ("uppromote", "UpPromote", ["uppromote.com"]),
    ("goaffpro", "GoAffPro", ["goaffpro.com"]),
    ("refersion", "Refersion", ["refersion.com"]),
    ("social_snowball", "Social Snowball", ["socialsnowball.io"]),
    ("bixgrow", "BixGrow", ["bixgrow.com"]),
    ("affiliatly", "Affiliatly", ["affiliatly.com"]),
    ("leaddyno", "LeadDyno", ["leaddyno.com"]),
    ("shareasale", "ShareASale", ["shareasale.com"]),
    ("impact", "impact.com", ["impact.com", "impactradius.com"]),
    ("awin", "Awin", ["awin.com"]),
    ("rakuten", "Rakuten Advertising", ["rakutenadvertising.com", "linksynergy.com"]),
    ("cj", "CJ Affiliate", ["cj.com"]),
    ("grin", "GRIN", ["grin.co", "grin.live"]),
    ("aspire", "Aspire", ["aspireiq.com", "aspire.io"]),
    ("brandbassador", "Brandbassador", ["brandbassador.com"]),
    ("roster", "Roster", ["getroster.com"]),
    ("superfiliate", "Superfiliate", ["superfiliate.com"]),
    ("socialladder", "SocialLadder", ["socialladderapp.com"]),
    ("upfluence", "Upfluence", ["upfluence.co", "upfluence.com"]),
    ("tapfiliate", "Tapfiliate", ["tapfiliate.com"]),
    ("firstpromoter", "FirstPromoter", ["firstpromoter.com"]),
    ("partnerstack", "PartnerStack", ["partnerstack.com"]),
    ("shopmy", "ShopMy", ["shopmy.us"]),
    ("ltk", "LTK", ["shopltk.com", "rewardstyle.com"]),
    ("levanta", "Levanta", ["levanta.io"]),
    ("trend", "Trend", ["trend.io"]),
    ("joinbrands", "JoinBrands", ["joinbrands.com"]),
    ("insense", "Insense", ["insense.pro"]),
    ("minisocial", "minisocial", ["minisocial.io"]),
    ("collabstr", "Collabstr", ["collabstr.com"]),
    ("saral", "SARAL", ["getsaral.com"]),
    ("referralcandy", "ReferralCandy", ["referralcandy.com"]),
    ("dovetale", "Dovetale", ["dovetale.com"]),
    ("everflow", "Everflow", ["everflow.io"]),
    ("partnerize", "Partnerize", ["partnerize.com", "pepperjam.com"]),
    ("kolsquare", "Kolsquare", ["kolsquare.com"]),
    ("stack_influence", "Stack Influence", ["stackinfluence.com"]),
    ("amazon_associates", "Amazon Associates", ["affiliate-program.amazon.com"]),
    ("onbrand", "Onbrand", ["onbrand.com"]),
    ("simple_affiliate", "Simple Affiliate", ["simpleaffiliate.app"]),
    ("snowball", "Snowball", ["snowball.club"]),
    ("promoty", "Promoty", ["promoty.io"]),
    ("influee", "Influee", ["influee.co"]),
    ("billo", "Billo", ["billo.app"]),
    ("afflr", "Affiliate Marketing by Conversion Bear", ["afflr.io"]),
    ("shoutout", "ShoutOut", ["shoutout.global"]),
    ("sellfy_aff", "Tune", ["go2cloud.org", "hasoffers.com"]),
    ("flexoffers", "FlexOffers", ["flexoffers.com"]),
    ("webgains", "Webgains", ["webgains.com"]),
    ("tradedoubler", "Tradedoubler", ["tradedoubler.com"]),
    ("daisycon", "Daisycon", ["daisycon.com"]),
    ("commission_factory", "Commission Factory", ["commissionfactory.com"]),
    ("affiliate_future", "AvantLink", ["avantlink.com"]),
    ("brandchamp", "BrandChamp", ["brandchamp.io"]),
    ("affiliatery", "Affiliatery", ["staqlab.com"]),
    ("trackdesk", "Trackdesk", ["trackdesk.com"]),
    ("post_affiliate_pro", "Post Affiliate Pro", ["postaffiliatepro.com"]),
    ("socialladder_app", "SocialLadder", ["rkiapps.com"]),
    ("trybe", "Trybe", ["jointrybe.com"]),
    ("rakuten_linkshare", "Rakuten Advertising", ["linkshare.com"]),
    ("recomsale", "Recomsale", ["recomsale.com"]),
    ("tradetracker", "TradeTracker", ["tradetracker.com"]),
    ("flair", "Flair", ["hasflair.com"]),
    ("enlistly", "Enlistly", ["enlistly.com"]),
    ("vwala", "Vwala", ["vwa.la"]),
    ("goaffpro_app", "GoAffPro", ["goaffpro.app"]),
    ("rudis", "Rudi's Link", ["rudislink.com"]),
]
# Hosted form tools. (key, label, host suffixes, optional path prefix)
FORM_TOOLS = [
    ("google_forms", "Google Forms", ["docs.google.com"], "/forms"),
    ("google_forms", "Google Forms", ["forms.gle"], ""),
    ("typeform", "Typeform", ["typeform.com"], ""),
    ("tally", "Tally", ["tally.so"], ""),
    ("jotform", "Jotform", ["jotform.com", "jotform.us", "jotfor.ms"], ""),
    ("airtable", "Airtable", ["airtable.com"], ""),
    ("hubspot", "HubSpot form", ["hsforms.com", "hsforms.net", "hubspotpagebuilder.com"], ""),
    ("formstack", "Formstack", ["formstack.com"], ""),
    ("wufoo", "Wufoo", ["wufoo.com"], ""),
    ("paperform", "Paperform", ["paperform.co"], ""),
    ("fillout", "Fillout", ["fillout.com"], ""),
    ("cognito", "Cognito Forms", ["cognitoforms.com"], ""),
    ("zoho_forms", "Zoho Forms", ["zohopublic.com", "zohopublic.eu", "zohopublic.in"], ""),
    ("ms_forms", "Microsoft Forms", ["forms.office.com", "forms.cloud.microsoft"], ""),
    ("surveymonkey", "SurveyMonkey", ["surveymonkey.com"], ""),
    ("formsite", "Formsite", ["formsite.com"], ""),
    ("monday_forms", "monday.com form", ["forms.monday.com"], ""),
    ("notion_forms", "Notion form", ["notion.site"], ""),
    ("klaviyo_page", "Klaviyo form", ["klaviyo.com"], "/"),
]
# Form widgets that only fill in after scripts run. Matched against the class and id of elements in the
# main content (never the header, footer or site-wide pop-ups), so a newsletter box does not count.
WIDGET_TOKENS = [
    ("klaviyo-form-", "form", "Form on the page"), ("globo-formbuilder", "form", "Form on the page"),
    ("hulkapps-form", "form", "Form on the page"), ("hulk_form", "form", "Form on the page"),
    ("powr-form-builder", "form", "Form on the page"), ("pf-form", "form", "Form on the page"),
    ("wpforms-form", "form", "Form on the page"), ("gform_wrapper", "form", "Form on the page"),
    ("wpcf7", "form", "Form on the page"), ("elementor-form", "form", "Form on the page"),
    ("fluentform", "form", "Form on the page"), ("forminator", "form", "Form on the page"),
    ("jotform-form", "external_form", "Jotform"), ("typeform-widget", "external_form", "Typeform"),
    ("hs-form", "external_form", "HubSpot form"), ("hbspt-form", "external_form", "HubSpot form"),
    ("uppromote", "platform", "UpPromote"), ("goaffpro", "platform", "GoAffPro"), ("bixgrow", "platform", "BixGrow"),
    ("social-snowball", "platform", "Social Snowball"), ("refersion", "platform", "Refersion"),
    ("snowball_affiliate", "platform", "Social Snowball"), ("affiliate-sign-up-form", "platform", "Social Snowball"),
    ("pxformgenerator", "form", "Form on the page"), ("pifyform", "form", "Form on the page"),
    ("aisle-form", "form", "Form on the page"), ("forms_inline", "form", "Form on the page"),
    ("am-reg--form", "form", "Form on the page"), ("sa-signup-form", "platform", "Simple Affiliate"),
]
WIDGET_ATTRS = [("data-tf-widget", "external_form", "Typeform"), ("data-tf-live", "external_form", "Typeform"),
                ("data-tally-src", "external_form", "Tally"), ("data-paperform-id", "external_form", "Paperform"),
                ("data-fillout-id", "external_form", "Fillout")]
SCRIPT_MARKERS = [("hbspt.forms.create", "external_form", "HubSpot form"), ("jotform.com/jsform", "external_form", "Jotform"),
                  ("tally.so/widgets/embed", "external_form", "Tally"), ("/a/goaffpro/", "platform", "GoAffPro"),
                  ("widgets.goaffpro.app", "platform", "GoAffPro"), ("socialladder.rkiapps.com", "platform", "SocialLadder"),
                  ("gotoaisle.com/embed-forms", "form", "Form on the page")]

# A link in the page's main content that invites the reader to apply, and where it may lead.
APPLY_LINK_TEXT = re.compile(r"\bapply\b|\bapplication\b|\bbecome\s+an?\b|\bjoin\s+(?:the|our|us|now|today|as)\b|\bsign\s?-?up\b|"
                             r"\bregister\b|\bget\s+started\b|\benrol+\b|\bstart\s+earning\b", re.I)
APPLY_LINK_BAD = re.compile(r"newsletter|mailing|wholesale|stockist|retailer|career|\bjobs?\b|subscri|log[\s-]?in|sign[\s-]?in|"
                            r"\bshop\b|\border|\bcart\b|password|/account|session|webinar|zoom", re.I)
PORTAL_LABELS = {"partner", "partners", "ambassador", "ambassadors", "affiliate", "affiliates", "insiders", "creators",
                 "creator", "collab", "collabs", "influencers", "influencer", "community", "team"}
PORTAL_PATH = re.compile(r"/(?:register|signup|sign-up|sign_up|apply|create-account|join)\b", re.I)
APPLY_PATH = re.compile(r"appl(?:y|ication)|sign-?up|regist|become|\bjoin|ambassador|affiliate|creator|influencer|collab", re.I)

CATEGORIES = [
    ("coffee", "Coffee", r"coffee|espresso|roaster|roastery|cold[\s-]?brew|kaffee|koffie|caff[eè]\b|\bcafe\b|\bbeans\b"),
    ("tea", "Tea and matcha", r"\bteas?\b|matcha|\bchai\b|yerba|\btee\b|tisane|teahouse|\boolong\b"),
    ("chocolate-sweets", "Chocolate, sweets and baked goods",
     r"chocolat|cacao|cocoa|\bcandy\b|candies|confection|sweets\b|cookie|bakery|\bbaked\b|brownie|macaron|fudge|toffee|"
     r"caramel|gumm(?:y|ies)|donut|doughnut|cupcake|dessert|ice[\s-]?cream|gelato|truffle|pastry|\bcakes?\b"),
    ("snacks", "Snacks",
     r"snack|jerky|granola|popcorn|\bchips\b|crisps|nut[\s-]?butter|peanut|almond|cashew|pistachio|trail[\s-]?mix|"
     r"\btreats\b|\bbites\b|\bpuffs\b|"
     r"protein[\s-]?bars?|pretzel|cracker|biltong|dried[\s-]?fruit|\bnuts\b|\bbars\b"),
    ("pantry", "Sauces, spices and pantry",
     r"hot[\s-]?sauce|\bsauces?\b|salsa|bbq|barbecue|\bspices?\b|seasoning|\brubs?\b|honey|maple|olive[\s-]?oil|vinegar|"
     r"\bjams?\b|preserves|pasta|noodle|ramen|pickle|mustard|ketchup|condiment|pantry|syrup|flour|grocery|gourmet|"
     r"\bfoods?\b|kimchi|\bsalt\b|\bghee\b|\bmeat\b|seafood|\bcheese\b|\bfarm\b"),
    ("drinks", "Drinks",
     r"beverage|\bdrinks?\b|\bsoda\b|sparkling|\bjuices?\b|kombucha|energy[\s-]?drink|hydration|electrolyte|\bwater\b|"
     r"lemonade|smoothie|mocktail|\bmixers?\b|seltzer|non[\s-]?alcoholic|\btonic\b"),
    ("supplements", "Supplements and nutrition",
     r"supplement|vitamin|\bprotein\b|nutrition|wellness|superfood|collagen|probiotic|mushroom|adaptogen|pre[\s-]?workout|"
     r"creatine|\bgreens\b|herbal|ayurved|nootropic|\bhealth\b|\bfitness\b|\bgym\b"),
    ("skincare-beauty", "Skincare and beauty",
     r"skin[\s-]?care|\bskin\b|beauty|cosmetic|makeup|\bserum\b|sunscreen|\bspf\b|lip[\s-]?balm|moisturi|facial|derma|"
     r"\bcreams?\b|eczema|\bacne\b|anti[\s-]?aging|"
     r"hair[\s-]?care|shampoo|\bbeard\b|grooming|\bnails?\b|\blash|fragrance|perfume|cologne|\bhair\b"),
    ("bath-body", "Soap, bath and body",
     r"\bsoaps?\b|\bbath\b|body[\s-]?care|deodorant|lotion|body[\s-]?butter|\bscrubs?\b|toothpaste|oral[\s-]?care|"
     r"personal[\s-]?care|shower|\bbalm\b|essential[\s-]?oils?|aromatherapy"),
    ("candles-home", "Candles and home",
     r"candle|wax[\s-]?melts?|home[\s-]?fragrance|diffuser|incense|home[\s-]?decor|cleaning|laundry|detergent|household|"
     r"\bhome\b|kitchenware|cookware"),
    ("pets", "Pets", r"\bpets?\b|\bdogs?\b|\bcats?\b|\bpuppy\b|\bpuppies\b|kitten|canine|feline|\bpaws?\b"),
    ("baby-kids", "Baby and kids", r"\bbaby\b|\bbabies\b|\bkids?\b|toddler|\binfant\b|\bmoms?\b|maternity|children"),
    ("apparel", "Apparel and accessories",
     r"apparel|clothing|\bwear\b|fashion|jewel|\bshoes?\b|sneaker|\bbags?\b|accessor|swimwear|activewear|\bhats?\b|\btees?\b|"
     r"lingerie|underwear|intimates|\bdress(?:es)?\b|boutique"),
    ("outdoors-sports", "Sports and outdoors",
     r"outdoor|\bsports?\b|cycling|\brunning\b|\bgolf\b|fishing|hunting|camping|\bsurf|climbing|\byoga\b|\bbike"),
]
CATEGORY_LABEL = {k: label for k, label, _ in CATEGORIES}
CATEGORY_LABEL["other"] = "Other brands"
_CATEGORY_RX = [(k, re.compile(rx, re.I)) for k, _, rx in CATEGORIES]

CC_TLD = {
    "au": "Australia", "uk": "United Kingdom", "ca": "Canada", "de": "Germany", "in": "India", "nz": "New Zealand",
    "nl": "Netherlands", "ch": "Switzerland", "ie": "Ireland", "za": "South Africa", "it": "Italy", "sg": "Singapore",
    "se": "Sweden", "br": "Brazil", "dk": "Denmark", "jp": "Japan", "fr": "France", "es": "Spain", "be": "Belgium",
    "at": "Austria", "no": "Norway", "fi": "Finland", "pt": "Portugal", "mx": "Mexico", "hk": "Hong Kong", "my": "Malaysia",
    "ph": "Philippines", "ae": "United Arab Emirates", "pl": "Poland", "gr": "Greece", "us": "United States",
    "pk": "Pakistan", "id": "Indonesia", "kr": "South Korea", "tw": "Taiwan", "il": "Israel", "cz": "Czechia",
}
LANG_NAME = {"en": "English", "de": "German", "fr": "French", "es": "Spanish", "nl": "Dutch", "it": "Italian",
             "pt": "Portuguese", "sv": "Swedish", "da": "Danish", "no": "Norwegian", "nb": "Norwegian", "fi": "Finnish",
             "ja": "Japanese", "pl": "Polish", "el": "Greek", "cs": "Czech", "ko": "Korean", "zh": "Chinese",
             "tr": "Turkish", "id": "Indonesian", "he": "Hebrew"}

SOCIALS = [("instagram", r"\binstagram\b|\binsta\b|\big\b"), ("tiktok", r"\btik\s?tok\b"), ("youtube", r"\byoutube\b"),
           ("facebook", r"\bfacebook\b"), ("pinterest", r"\bpinterest\b"), ("twitch", r"\btwitch\b"),
           ("x", r"\btwitter\b"), ("strava", r"\bstrava\b")]
_RES = r"(?:residents?\s+(?:only|of)|based\s+(?:only\s+)?in|only\s+(?:open|available)\s+(?:to|in)|live\s+in|located\s+in|living\s+in)"
RESIDENTS = [
    ("US", r"\b(?:u\.?s\.?a?\.?|united\s+states)[\s-]+(?:residents?|based|only)\b|" + _RES + r"\s+(?:the\s+)?(?:u\.?s\.?a?\.?(?![a-z])|united\s+states)"),
    ("GB", r"\b(?:u\.?k\.?|united\s+kingdom)[\s-]+(?:residents?|based|only)\b|" + _RES + r"\s+(?:the\s+)?(?:u\.?k\.?(?![a-z])|united\s+kingdom)"),
    ("CA", r"\b(?:canadian|canada)[\s-]+(?:residents?|based|only)\b|" + _RES + r"\s+canada\b"),
    ("AU", r"\b(?:australian|australia)[\s-]+(?:residents?|based|only)\b|" + _RES + r"\s+australia\b"),
]
RESIDENT_LABEL = {"US": "U.S. residents", "GB": "U.K. residents", "CA": "Canadian residents", "AU": "Australian residents"}
SOCIAL_LABEL = {"instagram": "Instagram", "tiktok": "TikTok", "youtube": "YouTube", "facebook": "Facebook",
                "pinterest": "Pinterest", "twitch": "Twitch", "x": "X (Twitter)", "strava": "Strava"}

_SKIP = {"script", "style", "noscript", "template", "svg"}
_CHROME = {"nav", "footer", "aside"}
_WS = re.compile(r"\s+")


def _clean(s):
    return _WS.sub(" ", s or "").strip()


class _Page(HTMLParser):
    """Collect the parts of a page the rules read. Tolerates broken markup."""

    def __init__(self, has_main=False):
        super().__init__(convert_charrefs=True)
        self.has_main = has_main     # the document has a <main> element: trust it over header/footer counting
        self.title, self.lang = "", ""
        self.meta = {}
        self.headings = []           # [(level, text)]
        self.links = []              # [(href, text, in_chrome)]
        self.iframes = []
        self.forms = []              # [{"action","fields":[...],"chrome":bool,"text":str}]
        self.text_main, self.text_all = [], []
        self._skip = 0
        self._chrome = 0
        self._main = 0
        self.saw_main = False
        self._in_title = False
        self._heading = None
        self._link = None
        self._form = None
        self.body_class = ""
        self.widgets = []            # [(method, label)] seen in the main content
        self._headers = []
        self._script = False

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag in _SKIP:
            self._skip += 1
            if tag == "script":
                self._script = True
                src = a.get("src", "").lower()
                for marker, method, label in SCRIPT_MARKERS:
                    if marker in src and self._in_content():
                        self.widgets.append((method, label))
            return
        if self._in_content():
            ident = (a.get("class", "") + " " + a.get("id", "")).lower()
            if ident.strip():
                for token, method, label in WIDGET_TOKENS:
                    if token in ident:
                        self.widgets.append((method, label))
                        break
            for attr, method, label in WIDGET_ATTRS:
                if attr in a:
                    self.widgets.append((method, label))
        if tag == "html":
            self.lang = a.get("lang", "")
        elif tag == "body":
            self.body_class = a.get("class", "")
        elif tag == "title" and not self.title:
            self._in_title = True
        elif tag == "meta":
            key = (a.get("name") or a.get("property") or "").lower()
            if key and key not in self.meta:
                self.meta[key] = a.get("content", "")
        elif tag == "header":
            outer = self._main == 0          # a site header; a <header> inside <main> is a section heading
            self._headers.append(outer)
            self._chrome += 1 if outer else 0
        elif tag in _CHROME:
            self._chrome += 1
        elif tag == "main":
            self._main += 1
            self.saw_main = True
        elif tag in ("h1", "h2", "h3"):
            self._heading = [int(tag[1]), []]
        elif tag == "a" and a.get("href"):
            self._link = [a["href"], [], not self._in_content()]
        elif tag == "iframe":
            src = a.get("src") or a.get("data-src")
            if src:
                self.iframes.append(src)
        elif tag == "form":
            self._form = {"action": a.get("action", ""), "id": a.get("id", ""), "cls": a.get("class", ""),
                          "role": a.get("role", ""), "fields": [], "chrome": not self._in_content(), "text": []}
        elif tag in ("input", "textarea", "select") and self._form is not None:
            self._form["fields"].append({
                "tag": tag, "type": (a.get("type") or tag).lower(), "name": a.get("name", ""), "id": a.get("id", ""),
                "placeholder": a.get("placeholder", ""), "value": a.get("value", "") if a.get("type") == "hidden" else ""})

    def _in_content(self):
        if self.has_main:
            return self._main > 0 and self._chrome == 0
        return self._chrome == 0

    def handle_endtag(self, tag):
        if tag in _SKIP:
            self._skip = max(0, self._skip - 1)
            if tag == "script":
                self._script = False
        elif tag == "title":
            self._in_title = False
        elif tag == "header":
            if self._headers and self._headers.pop():
                self._chrome = max(0, self._chrome - 1)
        elif tag in _CHROME:
            self._chrome = max(0, self._chrome - 1)
        elif tag == "main":
            self._main = max(0, self._main - 1)
        elif tag in ("h1", "h2", "h3") and self._heading:
            text = _clean(" ".join(self._heading[1]))
            if text:
                self.headings.append((self._heading[0], text, not self._in_content()))
            self._heading = None
        elif tag == "a" and self._link:
            self.links.append((self._link[0], _clean(" ".join(self._link[1])), self._link[2]))
            self._link = None
        elif tag == "form" and self._form is not None:
            self._form["text"] = _clean(" ".join(self._form["text"]))
            self.forms.append(self._form)
            self._form = None

    def handle_data(self, data):
        if self._in_title:
            self.title += data
            return
        if self._skip:
            if self._script and self._in_content():
                for marker, method, label in SCRIPT_MARKERS:
                    if marker in data:
                        self.widgets.append((method, label))
            return
        if self._heading is not None:
            self._heading[1].append(data)
        if self._link is not None:
            self._link[1].append(data)
        if self._form is not None:
            self._form["text"].append(data)
        self.text_all.append(data)
        if self._in_content():
            self.text_main.append(data)


def _host_matches(host, suffixes):
    return any(host == s or host.endswith("." + s) for s in suffixes)


def _platform_for(url):
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if not host:
        return None
    for key, label, suffixes in PLATFORMS:
        if _host_matches(host, suffixes):
            return ("platform", key, label)
    for key, label, suffixes, prefix in FORM_TOOLS:
        if _host_matches(host, suffixes) and (parts.path or "/").startswith(prefix or "/"):
            if key == "klaviyo_page" and not host.startswith("manage."):
                continue
            return ("external_form", key, label)
    return None


_FORM_SKIP_ACTION = re.compile(r"/search|/cart|/account|/localization|/checkout|/password|/challenge|subscri|newsletter|"
                               r"stock|notif|review|wishlist|/comments|klaviyo|list-manage|mailchimp|/login", re.I)
_FORM_SKIP_IDENT = re.compile(r"newsletter|subscri|stock|review|search|login|klaviyo|wishlist|comment|popup|footer", re.I)
_SOCIAL_FIELD = re.compile(r"instagram|tik\s?tok|youtube|handle|follower|social|channel|audience|portfolio|\burl\b|website|blog", re.I)


def _program_form(form):
    """Is this an inquiry or application form (rather than search, cart, login, review or newsletter)?"""
    if form["chrome"] or form.get("role") == "search" or _FORM_SKIP_ACTION.search(form["action"] or ""):
        return None
    if _FORM_SKIP_IDENT.search(f"{form.get('id', '')} {form.get('cls', '')}"):
        return None
    fields = [f for f in form["fields"] if f["type"] not in ("hidden", "submit", "button", "image", "reset")]
    if any(f["type"] == "password" for f in fields) and len(fields) < 4:
        return None  # a login form for people who already joined (a sign-up form asks for more)
    hidden = {f["name"]: f["value"] for f in form["fields"] if f["type"] == "hidden"}
    if hidden.get("form_type") in ("customer", "customer_login", "create_customer", "recover_customer_password",
                                   "product", "localization", "storefront_password", "cart", "new_comment"):
        return None
    names = " ".join(f"{f['name']} {f['id']} {f['placeholder']}" for f in fields)
    if re.search(r"rating|review|order[\s_-]*(?:number|id)|comment\[|recipient", names, re.I):
        return None
    has_email = any(f["type"] == "email" for f in fields) or re.search(r"e-?mail", names, re.I)
    has_text = any(f["tag"] == "textarea" for f in fields)
    social = bool(_SOCIAL_FIELD.search(names + " " + form.get("text", "")))
    if not has_email:
        return None
    if has_text or social or len(fields) >= 4:
        return {"social_fields": social, "fields": len(fields)}
    return None


def _first_number(s):
    s = s.replace(",", "").replace(" ", "")
    m = re.match(r"(\d+(?:\.\d+)?)([kKmM]?)", s)
    if not m:
        return None
    n = float(m.group(1)) * {"k": 1_000, "m": 1_000_000}.get(m.group(2).lower(), 1)
    return int(n)


def extract_facts(text):
    """Pull a few checkable details out of the page's own wording. Each is shown as "the page mentions"."""
    facts = {}
    low = text
    m = (re.search(r"(\d{1,2}(?:\.\d)?)\s?%\s+(?:commission|of\s+(?:each|every|all)\s+(?:sale|order)s?|on\s+(?:each|every|all)\s+(?:sale|order)s?|per\s+sale)", low, re.I)
         or re.search(r"commissions?\s+(?:of|rate\s+of|up\s+to|is|starting\s+at|:)?\s*(?:up\s+to\s+)?(\d{1,2}(?:\.\d)?)\s?%", low, re.I)
         or re.search(r"earn\s+(?:up\s+to\s+)?(\d{1,2}(?:\.\d)?)\s?%", low, re.I))
    if m:
        v = float(m.group(1))
        if 1 <= v <= 60:
            facts["commission_pct"] = int(v) if v == int(v) else v
    m = re.search(r"(\d{1,2})\s?%\s+(?:off|discount)", low, re.I) or re.search(r"discount\s+(?:code\s+)?(?:of\s+)?(\d{1,2})\s?%", low, re.I)
    if m and 5 <= int(m.group(1)) <= 70:
        facts["discount_pct"] = int(m.group(1))
    if re.search(r"\bfree\s+(?:products?|samples?|merch|gear|coffee|tea|goodies|swag|stuff|bags?|box(?:es)?)\b|\bcomplimentary\s+products?\b|"
                 r"\bgifted\s+products?\b|\bproducts?\s+(?:for\s+free|on\s+us)\b|\bsend\s+you\s+(?:free\s+)?(?:products?|samples?|a\s+(?:pr\s+)?(?:box|package))", low, re.I):
        facts["free_product"] = True
    if re.search(r"\bpaid\s+(?:collab\w*|partnerships?|campaigns?|opportunit\w+|content)\b|\bcash\s+(?:bonus|payments?|commission)\b|\bflat\s+fee\b", low, re.I):
        facts["paid"] = True
    m = re.search(r"(?:at\s+least|minimum(?:\s+of)?|min\.?|over|more\s+than|have)\s+(\d[\d,.]*\s?[kKmM]?)\+?\s*(?:instagram\s+|tiktok\s+|social\s+media\s+|social\s+)?(?:followers|subscribers)", low, re.I) \
        or re.search(r"\b(\d[\d,.]*\s?[kKmM]?)\+\s*(?:instagram\s+|tiktok\s+|social\s+)?(?:followers|subscribers)", low, re.I)
    if m:
        n = _first_number(m.group(1))
        if n and 100 <= n <= 5_000_000:
            facts["followers_min"] = n
    if re.search(r"\bno\s+(?:minimum\s+)?follower\s+(?:count\s+)?(?:minimum|requirement|count)\b|\bany\s+(?:size|follower\s+count)\b|"
                 r"\bregardless\s+of\s+(?:your\s+)?follower", low, re.I):
        facts["no_follower_minimum"] = True
    m = re.search(r"\bmust\s+be\s+(?:at\s+least\s+|over\s+)?(18|19|21)\b|\b(18|19|21)\s*(?:\+|years?\s+(?:of\s+age|old)\s+or\s+older|or\s+older)", low, re.I)
    if m:
        facts["min_age"] = int(m.group(1) or m.group(2))
    for code, rx in RESIDENTS:
        if re.search(rx, low, re.I):
            facts["residents"] = code
            break
    socials = [k for k, rx in SOCIALS if re.search(rx, low, re.I)]
    if socials:
        facts["platforms"] = socials
    return facts


def brand_name(page, host):
    """The brand's own name for itself: og:site_name, else the part of the title that matches the domain."""
    label = host.lower()
    for prefix in ("www.", "shop.", "store."):
        if label.startswith(prefix):
            label = label[len(prefix):]
    core = re.sub(r"[^a-z0-9]", "", label.split(".")[0])
    def pick(text):
        segs = [p for p in re.split(r"\s+[|–—·•:]\s+|\s+-\s+", _clean(text)) if p]
        for part in segs:
            folded = re.sub(r"[^a-z0-9]", "", part.lower())
            if folded and len(part) <= 60 and (folded in core or core in folded):
                return part
        return ""

    site = _clean(page.meta.get("og:site_name", ""))
    if site and len(site) <= 60 and not re.search(r"https?://|\.(?:com|co|net|org)\b", site, re.I) and not re.search(r"\s[|–—]\s", site):
        name = site
    else:
        name = pick(site) or pick(page.title)
        if not name and site and len(site) <= 60:
            name = re.split(r"\s+[|–—]\s+", site)[0]
    if not name:
        name = " ".join(w.capitalize() for w in re.split(r"[-_]", label.split(".")[0]) if w)
    name = re.sub(r"\s*[|–—-]\s*(?:official\s+(?:site|store|website)|online\s+store|shop\s+online).*$", "", name, flags=re.I)
    if re.search(r"ambassador|affiliate|influencer|\bprogram(?:me)?\b|collab|sign\s?up|\bapply\b", name, re.I):
        name = " ".join(w.capitalize() for w in re.split(r"[-_]", label.split(".")[0]) if w)
    return _clean(name)[:60]


def categorize(name, host, title="", description="", body=""):
    """Guess a product category from what the brand says about itself.

    The store's own description counts most, then its name and web address, then the page.
    """
    scores = {}
    label = host.lower()
    for prefix in ("www.", "shop.", "store."):
        if label.startswith(prefix):
            label = label[len(prefix):]
    glued = re.sub(r"[^a-z]", "", label.split(".")[0])  # 'bigbeancoffee'
    spaced = name + " " + re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
    for key, rx in _CATEGORY_RX:
        loose = re.compile(rx.pattern.replace(r"\b", ""), re.I)
        s = 5 * min(3, len(set(m.group(0).lower() for m in rx.finditer(description))))
        s += 3 if (rx.search(spaced) or loose.search(glued)) else 0
        s += 1 if rx.search(title) else 0
        s += min(2, len(set(m.group(0).lower() for m in rx.finditer(body[:6000])))) if not description else 0
        if s:
            scores[key] = s
    if not scores:
        return "other"
    order = [k for k, _ in _CATEGORY_RX]
    best = max(scores.items(), key=lambda kv: (kv[1], -order.index(kv[0])))
    return best[0] if best[1] >= 3 else "other"


COUNTRY = {"US": "United States", "GB": "United Kingdom", "AU": "Australia", "CA": "Canada", "DE": "Germany", "IN": "India",
           "NZ": "New Zealand", "NL": "Netherlands", "CH": "Switzerland", "IE": "Ireland", "ZA": "South Africa", "IT": "Italy",
           "SG": "Singapore", "SE": "Sweden", "BR": "Brazil", "DK": "Denmark", "JP": "Japan", "FR": "France", "ES": "Spain",
           "BE": "Belgium", "AT": "Austria", "NO": "Norway", "FI": "Finland", "PT": "Portugal", "MX": "Mexico",
           "HK": "Hong Kong", "MY": "Malaysia", "PH": "Philippines", "AE": "United Arab Emirates", "PL": "Poland",
           "GR": "Greece", "PK": "Pakistan", "ID": "Indonesia", "KR": "South Korea", "TW": "Taiwan", "IL": "Israel",
           "CZ": "Czechia", "TH": "Thailand", "VN": "Vietnam", "TR": "Turkey", "SA": "Saudi Arabia", "EG": "Egypt",
           "NG": "Nigeria", "KE": "Kenya", "CO": "Colombia", "CL": "Chile", "AR": "Argentina", "PE": "Peru", "RO": "Romania",
           "HU": "Hungary", "BG": "Bulgaria", "HR": "Croatia", "SI": "Slovenia", "SK": "Slovakia", "LT": "Lithuania",
           "LV": "Latvia", "EE": "Estonia", "LU": "Luxembourg", "MT": "Malta", "CY": "Cyprus", "IS": "Iceland",
           "LK": "Sri Lanka", "BD": "Bangladesh", "NP": "Nepal", "QA": "Qatar", "KW": "Kuwait", "BH": "Bahrain",
           "OM": "Oman", "JO": "Jordan", "LB": "Lebanon", "MA": "Morocco", "GH": "Ghana", "JM": "Jamaica",
           "TT": "Trinidad and Tobago", "PR": "Puerto Rico", "CR": "Costa Rica", "PA": "Panama", "DO": "Dominican Republic",
           "GT": "Guatemala", "EC": "Ecuador", "UY": "Uruguay", "CN": "China", "UA": "Ukraine", "RS": "Serbia"}


def region_for(host, lang):
    labels = host.lower().split(".")
    tld = labels[-1]
    if tld in CC_TLD and tld != "us":
        return CC_TLD[tld]
    if tld == "us":
        return "United States"
    m = re.match(r"^[a-z]{2}[-_]([A-Za-z]{2})$", lang or "")
    if m and m.group(1).lower() in CC_TLD:
        return CC_TLD[m.group(1).lower()]
    if m and m.group(1).lower() == "gb":
        return "United Kingdom"
    return ""


def analyse(html, url):
    """Return what the page says about itself. See the module docstring for the listing rule."""
    page = _Page(has_main=bool(re.search(r"<main[\s>]", html, re.I)))
    try:
        page.feed(html)
        page.close()
    except Exception:  # html.parser is lenient, but a pathological page must not stop a crawl
        pass
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    path_words = re.sub(r"[/_\-.+%]+", " ", parts.path)
    title = _clean(page.title)
    h1 = " ".join(t for lvl, t, chrome in page.headings if lvl == 1 and not chrome)
    h23 = " ".join(t for lvl, t, chrome in page.headings if lvl > 1 and not chrome)
    main_text = _clean(" ".join(page.text_main))
    all_text = _clean(" ".join(page.text_all))
    if len(main_text) < 200 and not page.has_main:
        main_text = all_text
    out = {"url": url, "title": title[:160], "brand": brand_name(page, host), "lang": (page.lang or "")[:8],
           "is_program": False, "reason": "", "types": [], "apply": None, "facts": {}, "category": "other",
           "region": region_for(host, page.lang), "closed": False, "challenge": False, "noindex": False}

    low_html = html[:400_000].lower()
    if CHALLENGE_TITLE.search(title) or (len(all_text) < 1500 and any(k in low_html for k in CHALLENGE_BODY)):
        out.update(challenge=True, reason="bot check shown instead of the page")
        return out
    if "password" in page.body_class.split() or re.search(r"/password/?$", parts.path) or \
            (re.search(r"opening\s+soon|coming\s+soon", title, re.I) and len(all_text) < 1500):
        out["reason"] = "store is password-protected or not open"
        return out
    robots_meta = (page.meta.get("robots", "") + "," + page.meta.get("googlebot", "")).lower()
    if "noindex" in robots_meta or "none" in [t.strip() for t in robots_meta.split(",")]:
        out.update(noindex=True, reason="page asks not to be indexed")
        return out
    if re.search(r"\b404\b|page\s+not\s+found|not\s+found", title, re.I) and len(main_text) < 3000:
        out["reason"] = "page not found"
        return out
    if re.search(r"/(?:contact|contact-us|contacto|kontakt|contactez-nous|get-in-touch)/?$", parts.path, re.I):
        out["reason"] = "a general contact page"
        return out
    if re.search(r"/(?:login|log-in|signin|sign-in)/?$", parts.path, re.I):
        out["reason"] = "a login page for people who already joined"
        return out

    if AGE_GATE.search(all_text[:20000]) or restricted(re.sub(r"[.\-_]", " ", host), title, page.meta.get("og:site_name", ""),
                                                      page.meta.get("description", "")):
        out["reason"] = "age-restricted store or product"
        return out
    if pay_to_join(main_text[:16000]):
        out["reason"] = "the page asks people to pay or buy a kit to join"
        return out
    headline = " ".join([path_words, title, h1])
    # --- which programs does the page name? ------------------------------------------------------
    scores = {}
    for key, _, strong_rx, body_rx in TYPES:
        s = 0
        if re.search(strong_rx, path_words, re.I):
            s += 3
        if re.search(strong_rx, title, re.I):
            s += 3
        if re.search(strong_rx, h1, re.I):
            s += 3
        if re.search(strong_rx, h23, re.I):
            s += 1
        s += min(2, len(re.findall(body_rx, main_text[:12000], re.I)) // 2)
        if s:
            scores[key] = s
    headline_types = [k for k in TYPE_ORDER if scores.get(k, 0) >= 3]
    creator_context = len(CREATOR_CONTEXT.findall(main_text[:12000]))

    if COMMERCIAL.search(headline) and not CREATOR_HEADLINE.search(headline):
        out["reason"] = "page is for wholesale, trade, careers, donations or another purpose"
        return out
    if re.search(r"corporate[\s_-]*gift", headline, re.I):
        out["reason"] = "corporate gifting sales page"
        return out
    specific = [k for k in headline_types if k != "collab"]
    if not specific and "collab" not in headline_types:
        out["reason"] = "address and headline do not name a creator, ambassador, affiliate or gifting program"
        return out
    if CLOSED.search(main_text[:12000]):
        out.update(closed=True, reason="the page says applications are closed or paused")
        return out

    # --- how does a person apply? -----------------------------------------------------------------
    apply = None
    candidates = []
    for href, text, chrome in page.links:
        if chrome:
            continue
        target = urljoin(url, href)
        hit = _platform_for(target)
        if hit:
            candidates.append(hit)
    for src in page.iframes:
        hit = _platform_for(urljoin(url, src))
        if hit:
            candidates.append(hit)
    platform_hits = [c for c in candidates if c[0] == "platform"]
    form_hits = [c for c in candidates if c[0] == "external_form"]
    native = [f for f in (_program_form(f) for f in page.forms) if f]
    widget = page.widgets[0] if page.widgets else None
    mailto = any(href.lower().startswith("mailto:") for href, _, chrome in page.links if not chrome)
    portal = link = False
    here = (parts.path or "/").rstrip("/")
    for href, text, chrome in page.links:
        if chrome or not APPLY_LINK_TEXT.search(text) or APPLY_LINK_BAD.search(text + " " + href):
            continue
        try:
            t = urlsplit(urljoin(url, href))
        except ValueError:
            continue
        thost = (t.hostname or "").lower()
        if t.scheme not in ("http", "https") or not thost:
            continue
        if thost == host:
            tpath = (t.path or "/").rstrip("/")
            if tpath and tpath != here and APPLY_PATH.search(tpath):
                link = True
        elif site_key(thost) == site_key(host):
            if thost.split(".")[0] in PORTAL_LABELS or PORTAL_PATH.search(t.path or ""):
                portal = True
    if platform_hits:
        apply = {"method": "platform", "provider": platform_hits[0][1], "label": platform_hits[0][2]}
    elif form_hits:
        apply = {"method": "external_form", "provider": form_hits[0][1], "label": form_hits[0][2]}
    elif native:
        apply = {"method": "form", "provider": "on_page", "label": "Form on the page"}
    elif widget:
        apply = {"method": widget[0], "label": widget[1],
                 "provider": "on_page" if widget[0] == "form" else re.sub(r"[^a-z0-9]+", "_", widget[1].lower()).strip("_")}
    elif portal:
        apply = {"method": "portal", "provider": "brand_portal", "label": "Sign-up portal on the brand's site"}
    elif link:
        apply = {"method": "link", "provider": "apply_page", "label": "Application page linked from this page"}
    elif mailto and APPLY_WORDS.search(main_text[:12000]):
        apply = {"method": "email", "provider": "email", "label": "Email address on the page"}
    if not apply:
        out["reason"] = "page names a program but shows no way to apply"
        return out
    if not specific and creator_context < 2 and apply["method"] != "platform":
        # "Collaborations" alone could mean other businesses: require creator wording or a creator platform.
        out["reason"] = "address and headline do not name a creator, ambassador, affiliate or gifting program"
        return out
    if not APPLY_WORDS.search(" ".join([title, h1, h23, main_text[:12000]])) and apply["method"] in ("form", "email"):
        out["reason"] = "page has a form but no invitation to apply"
        return out

    types = [k for k in TYPE_ORDER if scores.get(k, 0) >= 3]
    for k in TYPE_ORDER:  # running-text mentions add a type only when clearly present
        if k not in types and k != "collab" and scores.get(k, 0) >= 2:
            types.append(k)
    if apply.get("provider") == "shopify_collabs" and "creator" not in types:
        types.append("creator")  # Shopify Collabs exists to connect brands with creators
    types = [k for k in TYPE_ORDER if k in types]
    out.update(is_program=True, types=types, apply=apply, facts=extract_facts(main_text[:16000]),
               category=categorize(out["brand"], host, title, "", main_text))
    return out
