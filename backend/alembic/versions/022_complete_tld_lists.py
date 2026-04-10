"""Seed complete CZDS TLD access list and all OpenINTEL ccTLDs.

Revision ID: 022_complete_tld_lists
Revises: 021_seed_ingestion_tld_policy
Create Date: 2026-04-10 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "022_complete_tld_lists"
down_revision = "021_seed_ingestion_tld_policy"
branch_labels = None
depends_on = None

# ── CZDS approved TLDs (access = approved) ───────────────────────────────────
_CZDS_APPROVED = [
    "aaa", "aarp", "abb", "abbott", "abbvie", "abc", "able", "abogado", "abudhabi",
    "academy", "accenture", "accountant", "accountants", "aco", "actor", "ads", "adult",
    "aeg", "aetna", "afl", "africa", "agakhan", "agency", "aig", "airbus", "airforce",
    "akdn", "alibaba", "alipay", "allfinanz", "allstate", "ally", "alsace",
    "americanexpress", "americanfamily", "amex", "amfam", "amica", "amsterdam",
    "analytics", "android", "anquan", "anz", "aol", "apartments", "app", "apple",
    "aquarelle", "arab", "aramco", "archi", "army", "art", "arte", "asda", "associates",
    "athleta", "attorney", "auction", "audi", "audible", "audio", "auspost", "author",
    "auto", "autos", "aws", "axa", "azure",
    "baby", "baidu", "banamex", "band", "bank", "bar", "barcelona", "barclaycard",
    "barclays", "barefoot", "bargains", "baseball", "basketball", "bauhaus", "bayern",
    "bbc", "bbt", "bbva", "bcg", "bcn", "beats", "beauty", "beer", "berlin", "best",
    "bestbuy", "bet", "bharti", "bible", "bid", "bike", "bing", "bingo", "bio", "black",
    "blackfriday", "blockbuster", "blog", "bloomberg", "blue", "bms", "bmw", "boats",
    "boehringer", "bofa", "bom", "bond", "boo", "book", "booking", "bosch", "bostik",
    "boston", "bot", "boutique", "box", "bradesco", "bridgestone", "broadway", "broker",
    "brother", "brussels", "build", "builders", "business", "buy", "buzz",
    "cab", "cafe", "cal", "call", "calvinklein", "cam", "camera", "camp", "canon",
    "capetown", "capital", "capitalone", "car", "caravan", "cards", "care", "career",
    "careers", "cars", "casa", "case", "cash", "casino", "cat", "catering", "catholic",
    "cba", "cbn", "cbre", "center", "ceo", "cern", "cfa", "cfd", "chanel", "channel",
    "charity", "chase", "chat", "cheap", "chintai", "christmas", "chrome", "church",
    "cipriani", "circle", "cisco", "citadel", "citi", "citic", "city", "claims",
    "cleaning", "click", "clinic", "clinique", "clothing", "cloud", "club", "clubmed",
    "coach", "codes", "coffee", "college", "cologne", "commbank", "community", "company",
    "compare", "computer", "comsec", "condos", "construction", "consulting", "contact",
    "contractors", "cooking", "cool", "coop", "corsica", "country", "coupon", "coupons",
    "courses", "credit", "creditcard", "creditunion", "cricket", "crown", "crs", "cruise",
    "cruises", "cuisinella", "cymru", "cyou",
    "dad", "dance", "data", "date", "dating", "datsun", "day", "dclk", "dds", "deal",
    "dealer", "deals", "degree", "delivery", "dell", "deloitte", "delta", "democrat",
    "dental", "dentist", "desi", "design", "dev", "dhl", "diamonds", "diet", "digital",
    "direct", "directory", "discount", "discover", "dish", "diy", "dnp", "docs",
    "doctor", "dog", "domains", "dot", "download", "drive", "dtv", "dupont", "durban",
    "dvag", "dvr",
    "earth", "eat", "eco", "edeka", "education", "email", "emerck", "energy", "engineer",
    "engineering", "enterprises", "epson", "equipment", "ericsson", "esq", "estate",
    "eurovision", "eus", "events", "exchange", "expert", "exposed", "express",
    "extraspace",
    "fage", "fail", "fairwinds", "faith", "family", "fan", "fans", "farm", "farmers",
    "fashion", "fast", "fedex", "feedback", "ferrari", "ferrero", "fidelity", "fido",
    "film", "final", "finance", "financial", "fire", "firestone", "firmdale", "fish",
    "fishing", "fit", "fitness", "flickr", "flights", "flir", "florist", "flowers",
    "fly", "foo", "food", "football", "forex", "forsale", "forum", "foundation", "fox",
    "free", "fresenius", "frl", "frogans", "frontier", "ftr", "fujitsu", "fun", "fund",
    "furniture", "futbol", "fyi",
    "gal", "gallery", "gallo", "gallup", "game", "games", "gap", "garden", "gbiz",
    "gea", "gent", "genting", "george", "ggee", "gift", "gifts", "gives", "giving",
    "glass", "gle", "global", "globo", "gmail", "gmbh", "gmo", "gmx", "godaddy", "gold",
    "goldpoint", "golf", "goodyear", "goog", "google", "gop", "got", "grainger",
    "graphics", "gratis", "green", "gripe", "grocery", "group", "gucci", "guge",
    "guide", "guitars", "guru",
    "hair", "hamburg", "hangout", "haus", "hbo", "hdfc", "hdfcbank", "health",
    "healthcare", "help", "here", "hermes", "hiphop", "hisamitsu", "hitachi", "hiv",
    "hkt", "hockey", "holdings", "holiday", "homedepot", "homegoods", "homes",
    "homesense", "honda", "horse", "hospital", "host", "hosting", "hot", "hotels",
    "hotmail", "house", "how", "hsbc", "hughes", "hyatt", "hyundai",
    "ibm", "icbc", "ice", "icu", "ieee", "ifm", "ikano", "imamat", "imdb", "immo",
    "immobilien", "inc", "industries", "infiniti", "ing", "ink", "institute",
    "insurance", "insure", "international", "intuit", "investments", "ipiranga",
    "irish", "ismaili", "ist", "istanbul", "itau", "itv",
    "jaguar", "java", "jcb", "jeep", "jetzt", "jewelry", "jio", "jll", "jmp", "jnj",
    "jobs", "joburg", "jot", "joy", "jpmorgan", "jprs", "juegos", "juniper",
    "kaufen", "kddi", "kerryhotels", "kerryproperties", "kfh", "kia", "kim", "kindle",
    "kitchen", "kiwi", "koeln", "komatsu", "kosher", "kpmg", "kpn", "krd", "kred",
    "kuokgroup", "kyoto",
    "lacaixa", "lamborghini", "lamer", "land", "landrover", "lanxess", "lasalle",
    "lat", "latino", "latrobe", "law", "lawyer", "lds", "lease", "leclerc", "lefrak",
    "legal", "lego", "lexus", "lgbt", "lidl", "life", "lifeinsurance", "lifestyle",
    "lighting", "like", "lilly", "limited", "limo", "link", "live", "living", "llc",
    "loan", "loans", "locker", "locus", "lol", "london", "lotte", "lotto", "love",
    "lpl", "lplfinancial", "ltd", "ltda", "lundbeck", "luxe", "luxury",
    "madrid", "maif", "maison", "makeup", "man", "management", "mango", "map", "market",
    "marketing", "markets", "marriott", "marshalls", "mattel", "mba", "mckinsey", "med",
    "media", "meet", "melbourne", "meme", "memorial", "men", "menu", "miami",
    "microsoft", "mini", "mint", "mit", "mitsubishi", "mlb", "mls", "mma", "mobi",
    "mobile", "moda", "moe", "moi", "mom", "monash", "money", "monster", "mormon",
    "mortgage", "moto", "motorcycles", "mov", "movie", "mtn", "mtr", "museum",
    "nab", "nagoya", "navy", "nba", "nec", "net", "netbank", "netflix", "network",
    "neustar", "new", "news", "next", "nextdirect", "nexus", "nfl", "ngo", "nhk",
    "nico", "nike", "nikon", "ninja", "nissan", "nissay", "nokia", "norton", "now",
    "nowruz", "nowtv", "nra", "nrw", "ntt", "nyc",
    "obi", "observer", "office", "okinawa", "olayan", "olayangroup", "ollo", "omega",
    "one", "ong", "onl", "online", "ooo", "open", "oracle", "orange", "organic",
    "origins", "osaka", "otsuka", "ott", "ovh",
    "page", "panasonic", "paris", "pars", "partners", "parts", "party", "pay", "pccw",
    "pet", "pfizer", "pharmacy", "phd", "philips", "phone", "photo", "photography",
    "photos", "physio", "pics", "pictet", "pictures", "pid", "pin", "ping", "pink",
    "pioneer", "pizza", "place", "play", "playstation", "plumbing", "plus", "pnc",
    "pohl", "poker", "politie", "porn", "praxi", "press", "prime", "pro", "prod",
    "productions", "prof", "progressive", "promo", "properties", "property",
    "protection", "pru", "prudential", "pub", "pwc",
    "qpon", "quebec", "quest",
    "racing", "radio", "read", "realestate", "realtor", "realty", "recipes", "red",
    "redumbrella", "rehab", "reise", "reisen", "reit", "reliance", "ren", "rent",
    "rentals", "repair", "report", "republican", "rest", "restaurant", "review",
    "reviews", "rexroth", "rich", "richardli", "ricoh", "ril", "rio", "rip", "rocks",
    "rodeo", "rogers", "room", "rsvp", "rugby", "ruhr", "run", "rwe", "ryukyu",
    "saarland", "safe", "safety", "sakura", "sale", "salon", "samsclub", "samsung",
    "sandvik", "sandvikcoromant", "sanofi", "sap", "sarl", "sas", "save", "saxo",
    "sbi", "sbs", "scb", "schaeffler", "schmidt", "scholarships", "school", "schule",
    "schwarz", "science", "search", "seat", "secure", "security", "seek", "select",
    "sener", "services", "seven", "sew", "sex", "sexy", "sfr", "shangrila", "sharp",
    "shell", "shia", "shiksha", "shoes", "shop", "shopping", "shouji", "show", "silk",
    "sina", "singles", "site", "ski", "skin", "sky", "skype", "sling", "smart",
    "smile", "sncf", "soccer", "social", "softbank", "software", "sohu", "solar",
    "solutions", "song", "sony", "soy", "space", "sport", "spot", "srl", "stada",
    "staples", "star", "statebank", "statefarm", "stc", "stcgroup", "stockholm",
    "storage", "store", "stream", "studio", "study", "style", "sucks", "supplies",
    "supply", "support", "surf", "surgery", "suzuki", "swatch", "swiss", "sydney",
    "systems",
    "tab", "talk", "taobao", "target", "tatamotors", "tatar", "tattoo", "tax", "taxi",
    "tci", "tdk", "team", "tech", "technology", "tel", "temasek", "tennis", "teva",
    "thd", "theater", "theatre", "tiaa", "tickets", "tienda", "tips", "tires", "tirol",
    "tjmaxx", "tjx", "tkmaxx", "tmall", "today", "tokyo", "tools", "top", "toray",
    "toshiba", "tours", "town", "toyota", "toys", "trade", "trading", "training",
    "travel", "travelers", "travelersinsurance", "trust", "trv", "tube", "tui",
    "tunes", "tushu", "tvs",
    "ubank", "ubs", "unicom", "university", "uno", "uol", "ups",
    "vacations", "vana", "vanguard", "vegas", "ventures", "verisign", "versicherung",
    "vet", "viajes", "video", "vig", "viking", "villas", "vin", "vip", "virgin",
    "visa", "vision", "viva", "vivo", "vlaanderen", "vodka", "volvo", "voto", "voyage",
    "wales", "walmart", "walter", "wang", "wanggou", "watch", "watches", "weather",
    "weatherchannel", "webcam", "weber", "website", "wed", "wedding", "weibo", "weir",
    "whoswho", "wien", "wiki", "win", "windows", "wine", "winners", "wme", "woodside",
    "work", "works", "world", "wow", "wtc", "wtf",
    "xbox", "xerox", "xihuan", "xin",
    "xn--11b4c3d", "xn--1ck2e1b", "xn--1qqw23a", "xn--30rr7y", "xn--3ds443g",
    "xn--3pxu8k", "xn--42c2d9a", "xn--45q11c", "xn--4gbrim", "xn--55qw42g",
    "xn--55qx5d", "xn--5su34j936bgsg", "xn--5tzm5g", "xn--6frz82g", "xn--8y0a063a",
    "xn--9dbq2a", "xn--9et52u", "xn--9krt00a", "xn--b4w605ferd", "xn--bck1b9a5dre4c",
    "xn--c1avg", "xn--c2br7g", "xn--cck2b3b", "xn--cg4bki", "xn--czrs0t",
    "xn--d1acj3b", "xn--eckvdtc9d", "xn--efvy88h", "xn--fct429k", "xn--fhbei",
    "xn--fiq228c5hs", "xn--fiq64b", "xn--fjq720a", "xn--flw351e", "xn--fzys8d69uvgm",
    "xn--gckr3f0f", "xn--gk3at1e", "xn--i1b6b1a6a2e", "xn--imr513n", "xn--io0a7i",
    "xn--j1aef", "xn--jvr189m", "xn--kcrx77d1x4a", "xn--mgba3a3ejt",
    "xn--mgba7c0bbn0a", "xn--mgbab2bd", "xn--mgbca7dzdo", "xn--mgbi4ecexp",
    "xn--mgbt3dhd", "xn--mk1bu44c", "xn--ngbc5azd", "xn--ngbe9e0a", "xn--ngbrx",
    "xn--nqv7f", "xn--nqv7fs00ema", "xn--nyqy26a", "xn--otu796d", "xn--p1acf",
    "xn--pssy2u", "xn--q9jyb4c", "xn--qcka1pmc", "xn--rhqv96g", "xn--rovu88b",
    "xn--t60b56a", "xn--tckwe", "xn--tiq49xqyj", "xn--unup4y",
    "xn--vermgensberater-ctb", "xn--vermgensberatung-pwb", "xn--vhquv", "xn--vuq861b",
    "xn--w4r85el8fhu5dnra", "xn--w4rs40l", "xn--xhq521b", "xn--zfr164b",
    "xxx", "xyz",
    "yachts", "yahoo", "yamaxun", "yandex", "yodobashi", "yoga", "yokohama", "you",
    "youtube", "yun",
    "zappos", "zara", "zero", "zip", "zone", "zuerich",
    # Additional gTLDs from bottom of access list
    "gay", "cpa", "biz", "org", "llp", "asia", "amazon", "xn--jlq480n2rg",
    "xn--cckwcxetd", "info", "com", "spa", "music", "kids", "name", "gov", "aero",
]

# CZDS pending TLDs — seeded as disabled until access is fully approved
_CZDS_PENDING = [
    "airtel", "bzh", "dubai", "ford", "gdn", "helsinki", "lincoln", "merckmsd",
    "moscow", "msd", "voting", "williamhill", "xn--80adxhks", "xn--czr694b",
    "xn--g2xx48c", "xn--kput3i", "xn--ses554g",
]

# ── OpenINTEL ccTLD list (from public S3 bucket listing) ─────────────────────
_OPENINTEL_CCTLDS = [
    # Latin-script ccTLDs
    "ac", "ad", "ae", "af", "ag", "ai", "al", "am", "ao", "aq", "ar", "as", "at",
    "au", "aw", "ax", "az", "ba", "bb", "bd", "be", "bf", "bg", "bh", "bi", "bj",
    "bm", "bn", "bo", "br", "bs", "bt", "bw", "by", "bz", "ca", "cc", "cd", "cf",
    "cg", "ch", "ci", "ck", "cl", "cm", "cn", "co", "cr", "cu", "cv", "cw", "cx",
    "cy", "cz", "de", "dj", "dk", "dm", "do", "dz", "ec", "ee", "eg", "er", "es",
    "et", "eu", "fi", "fj", "fk", "fm", "fo", "fr", "ga", "gd", "ge", "gf", "gg",
    "gh", "gi", "gl", "gm", "gn", "gp", "gq", "gr", "gs", "gt", "gu", "gw", "gy",
    "hk", "hm", "hn", "hr", "ht", "hu", "id", "ie", "il", "im", "in", "io", "iq",
    "ir", "is", "it", "je", "jm", "jo", "jp", "ke", "kg", "kh", "ki", "km", "kn",
    "kp", "kr", "kw", "ky", "kz", "la", "lb", "lc", "li", "lk", "lr", "ls", "lt",
    "lu", "lv", "ly", "ma", "mc", "md", "me", "mg", "mh", "mk", "ml", "mm", "mn",
    "mo", "mp", "mq", "mr", "ms", "mt", "mu", "mv", "mw", "mx", "my", "mz", "na",
    "nc", "ne", "nf", "ng", "ni", "nl", "no", "np", "nr", "nu", "nz", "om", "pa",
    "pe", "pf", "pg", "ph", "pk", "pl", "pm", "pn", "pr", "ps", "pt", "pw", "py",
    "qa", "re", "ro", "rs", "ru", "rw", "sa", "sb", "sc", "sd", "se", "sg", "sh",
    "si", "sk", "sl", "sm", "sn", "so", "sr", "ss", "st", "su", "sv", "sx", "sy",
    "sz", "tc", "td", "tf", "tg", "th", "tj", "tk", "tl", "tm", "tn", "to", "tr",
    "tt", "tv", "tw", "tz", "ua", "ug", "uk", "us", "uy", "uz", "va", "vc", "ve",
    "vg", "vi", "vn", "vu", "wf", "ws", "ye", "yt", "za", "zm", "zw",
    # IDN ccTLDs
    "xn--2scrj9c", "xn--3e0b707e", "xn--3hcrj9c", "xn--45br5cyl", "xn--45brj9c",
    "xn--4dbrk0ce", "xn--54b7fta0cc", "xn--80ao21a", "xn--90a3ac", "xn--90ae",
    "xn--90ais", "xn--clchc0ea0b2g2a9gcd", "xn--d1alf", "xn--e1a4c", "xn--fiqs8s",
    "xn--fiqz9s", "xn--fpcrj9c3d", "xn--fzc2c9e2c", "xn--gecrj9c", "xn--h2breg3eve",
    "xn--h2brj9c", "xn--h2brj9c8c", "xn--j1amh", "xn--j6w193g", "xn--kprw13d",
    "xn--kpry57d", "xn--l1acc", "xn--lgbbat1ad8j", "xn--mgb9awbf", "xn--mgba3a4f16a",
    "xn--mgbaam7a8h", "xn--mgbah1a3hjkrd", "xn--mgbai9azgqp6j", "xn--mgbayh7gpa",
    "xn--mgbbh1a", "xn--mgbbh1a71e", "xn--mgbcpq6gpa1a", "xn--mgberp4a5d4ar",
    "xn--mgbgu82a", "xn--mgbpl2fh", "xn--mgbtx2b", "xn--mix891f", "xn--node",
    "xn--o3cw4h", "xn--ogbpf8fl", "xn--p1ai", "xn--pgbs0dh", "xn--q7ce6a",
    "xn--qxa6a", "xn--qxam", "xn--rvc1e0am3e", "xn--s9brj9c", "xn--wgbh1c",
    "xn--wgbl6a", "xn--xkc2al3hye2a", "xn--xkc2dl3a5ee0h", "xn--y9a3aq",
    "xn--yfro4i67o", "xn--ygbi2ammx",
]


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Seed czds_tld_policy with approved TLDs (enabled)
    for tld in _CZDS_APPROVED:
        conn.execute(
            sa.text(
                "INSERT INTO czds_tld_policy "
                "(tld, is_enabled, priority, cooldown_hours, failure_count, updated_at) "
                "VALUES (:tld, true, 100, 24, 0, now()) "
                "ON CONFLICT (tld) DO NOTHING"
            ),
            {"tld": tld},
        )

    # 2. Seed czds_tld_policy with pending TLDs (disabled — await approval)
    for tld in _CZDS_PENDING:
        conn.execute(
            sa.text(
                "INSERT INTO czds_tld_policy "
                "(tld, is_enabled, priority, cooldown_hours, failure_count, updated_at) "
                "VALUES (:tld, false, 100, 24, 0, now()) "
                "ON CONFLICT (tld) DO NOTHING"
            ),
            {"tld": tld},
        )

    # 3. Sync all czds_tld_policy rows to ingestion_tld_policy (preserves existing state)
    conn.execute(
        sa.text(
            "INSERT INTO ingestion_tld_policy (source, tld, is_enabled) "
            "SELECT 'czds', tld, is_enabled FROM czds_tld_policy "
            "ON CONFLICT (source, tld) DO NOTHING"
        )
    )

    # 4. Seed OpenINTEL CCTLDs (enabled by default)
    for tld in _OPENINTEL_CCTLDS:
        conn.execute(
            sa.text(
                "INSERT INTO ingestion_tld_policy (source, tld, is_enabled) "
                "VALUES ('openintel', :tld, true) "
                "ON CONFLICT (source, tld) DO NOTHING"
            ),
            {"tld": tld},
        )


def downgrade() -> None:
    conn = op.get_bind()

    # Remove only the TLDs added by this migration; preserve pre-existing rows
    all_czds = _CZDS_APPROVED + _CZDS_PENDING
    for tld in all_czds:
        conn.execute(
            sa.text(
                "DELETE FROM czds_tld_policy WHERE tld = :tld "
                "AND failure_count = 0 AND notes IS NULL"  # only rows we inserted
            ),
            {"tld": tld},
        )

    for tld in _OPENINTEL_CCTLDS:
        conn.execute(
            sa.text(
                "DELETE FROM ingestion_tld_policy WHERE source = 'openintel' AND tld = :tld"
            ),
            {"tld": tld},
        )
