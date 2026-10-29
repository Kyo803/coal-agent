"""Curated cybersecurity / bug-bounty knowledge base for ROX N.

This is reference data, not an exploit kit. Two things it deliberately does:

  * it puts AUTHORISATION first -- a target is only in scope if the program's
    policy says it is, and testing anything else is a crime in most
    jurisdictions, not "grey area";
  * it separates "where to learn / who pays bounties" from "how to break
    things", so the agent can point a user at the right programme before it
    ever discusses technique.

URLs are bare domains. They are stable, well-known resources, but always
confirm the live URL and the programme's current policy before acting.
"""
from __future__ import annotations

import re

# --------------------------------------------------------------------------
# Bug bounty platforms (they host many programmes)
# --------------------------------------------------------------------------
PLATFORMS = [
    ("HackerOne", "hackerone.com", "largest bounty platform; Hacktivity is public"),
    ("Bugcrowd", "bugcrowd.com", "platform + public disclosure programme"),
    ("Intigriti", "intigriti.com", "EU-focused platform, strong writeups"),
    ("YesWeHack", "yeswehack.com", "EU/FR platform"),
    ("Synack", "synack.com", "vetted researcher network"),
    ("Cobalt", "cobalt.io", "pentest-as-a-service + bounty"),
    ("Immunefi", "immunefi.com", "Web3 / smart-contract bounties"),
    ("HackenProof", "hackenproof.com", "crypto + web3 bounties"),
    ("Zerocopter", "zerocopter.com", "EU platform"),
    ("Open Bug Bounty", "openbugbounty.org", "coordinated disclosure, no payout"),
    ("Federacy", "federacy.com", "boutique bounty platform"),
    ("HackTrophy", "hacktrophy.com", "EU platform"),
    ("Yogosha", "yogosha.com", "EU platform"),
    ("Secuna", "secuna.io", "APAC platform"),
    ("RedStorm", "redstorm.io", "platform + VDP"),
    ("BugBounter", "bugbounter.com", "platform"),
    ("Bugbase", "bugbase.in", "India-focused platform"),
    ("huntr", "huntr.dev", "AI/ML and open-source bounties"),
    ("0din", "0din.ai", "Mozilla GenAI bug bounty"),
    ("Code4rena", "code4rena.com", "smart-contract audit contests"),
    ("Sherlock", "sherlock.xyz", "smart-contract audit contests"),
    ("Cantina", "cantina.xyz", "smart-contract audits"),
    ("Hats Finance", "hats.finance", "on-chain bounties"),
    ("Detectify Crowdsource", "detectify.com/crowdsource", "web vuln research"),
    ("Safehats", "safehats.com", "platform"),
]

# --------------------------------------------------------------------------
# Vendor / VDP programmes (each pays or credits, own scope)
# --------------------------------------------------------------------------
VDP = [
    ("Google VRP", "bughunters.google.com", "Google/Alphabet"),
    ("Microsoft MSRC", "microsoft.com/msrc", "Windows/Azure/Office"),
    ("Apple Security Bounty", "security.apple.com", "iOS/macOS"),
    ("Meta Bug Bounty", "bugbounty.meta.com", "Facebook/Instagram/WhatsApp"),
    ("GitHub Security", "bounty.github.com", "GitHub + open source"),
    ("Mozilla", "mozilla.org/security/bug-bounty", "Firefox"),
    ("AWS", "aws.amazon.com/security/vulnerability-reporting", "cloud"),
    ("Cloudflare", "hackerone.com/cloudflare", "edge/network"),
    ("Intel", "intel.com/security", "hardware/firmware"),
    ("NVIDIA", "nvidia.com/object/product-security.html", "GPU/driver"),
    ("Cisco", "cisco.com/go/security", "network gear"),
    ("Oracle", "oracle.com/security-alerts", "database/Java"),
    ("Adobe", "adobe.com/security.html", "Creative/PDF"),
    ("Zoom", "hackerone.com/zoom", "video"),
    ("Dropbox", "hackerone.com/dropbox", "storage"),
    ("Shopify", "hackerone.com/shopify", "commerce"),
    ("Uber", "hackerone.com/uber", "mobility"),
    ("Coinbase", "hackerone.com/coinbase", "crypto exchange"),
    ("Kraken", "hackerone.com/kraken", "crypto exchange"),
    ("Zerodha", "zerodha.tech", "Indian brokerage VDP"),
    ("ZDI", "zerodayinitiative.com", "brokers + Pwn2Own"),
    ("SSD Secure Disclosure", "ssd-disclosure.com", "broker"),
    ("Pwn2Own (ZDI programme)", "zerodayinitiative.com/pwn2own",
     "contest, large prizes"),
]

# --------------------------------------------------------------------------
# Forums / communities
# --------------------------------------------------------------------------
FORUMS = [
    ("r/netsec", "reddit.com/r/netsec", "high-signal news + research"),
    ("r/AskNetsec", "reddit.com/r/AskNetsec", "questions, career"),
    ("r/bugbounty", "reddit.com/r/bugbounty", "bounty-specific"),
    ("r/cybersecurity", "reddit.com/r/cybersecurity", "general"),
    ("r/blueteamsec", "reddit.com/r/blueteamsec", "defence"),
    ("r/redteamsec", "reddit.com/r/redteamsec", "offence"),
    ("r/Pentesting", "reddit.com/r/Pentesting", "pentest"),
    ("r/ReverseEngineering", "reddit.com/r/ReverseEngineering", "RE"),
    ("r/Malware", "reddit.com/r/Malware", "malware analysis"),
    ("r/DFIR", "reddit.com/r/DFIR", "incident response"),
    ("r/ThreatIntel", "reddit.com/r/ThreatIntel", "CTI"),
    ("r/OSINT", "reddit.com/r/OSINT", "open-source intel"),
    ("r/websecurity", "reddit.com/r/websecurity", "web"),
    ("r/ApplicationSecurity", "reddit.com/r/ApplicationSecurity", "appsec"),
    ("r/cryptography", "reddit.com/r/cryptography", "crypto"),
    ("r/awssecurity", "reddit.com/r/awssecurity", "cloud"),
    ("r/CTF", "reddit.com/r/CTF", "competitions"),
    ("r/hacking", "reddit.com/r/hacking", "general"),
    ("Security StackExchange", "security.stackexchange.com", "Q&A"),
    ("RE StackExchange", "reverseengineering.stackexchange.com", "Q&A"),
    ("Crypto StackExchange", "crypto.stackexchange.com", "Q&A"),
    ("Hacker News", "news.ycombinator.com", "industry"),
    ("Lobsters", "lobste.rs", "technical"),
    ("0x00sec", "0x00sec.org", "low-level / RE"),
    ("SANS ISC", "isc.sans.edu", "diaries + handlers"),
    ("BleepingComputer", "bleepingcomputer.com/forums", "news + forums"),
    ("MalwareTips", "malwaretips.com", "consumer security"),
    ("Wilders Security", "wilderssecurity.com", "long-running forum"),
    ("Spiceworks", "community.spiceworks.com", "IT/ops"),
    ("HackerOne Community", "hackerone.com/community", "official"),
    ("OWASP Slack", "owasp.org/slack/invite", "appsec"),
    ("TryHackMe Discord", "tryhackme.com", "learning community"),
    ("Hack The Box Discord", "hackthebox.com", "labs community"),
    ("NahamSec Discord", "discord.gg/nahamsec", "bounty community"),
    ("Blue Team Village", "blueteamvillage.org", "defence community"),
    ("Black Hills InfoSec Discord", "blackhillsinfosec.com", "training"),
    ("SpecterOps", "specterops.io", "AD/identity research"),
    ("GitHub Security Lab", "securitylab.github.com", "research"),
    ("Google Project Zero", "googleprojectzero.blogspot.com", "zero-days"),
    ("PortSwigger Research", "portswigger.net/research", "web research"),
    ("Trail of Bits", "blog.trailofbits.com", "deep technical"),
    ("NCC Group Research", "research.nccgroup.com", "research"),
    ("Snyk", "snyk.io/blog", "appsec"),
    ("Rapid7", "rapid7.com/blog", "vuln research"),
    ("Qualys", "qualys.com/blog", "vuln mgmt"),
    ("Tenable", "tenable.com/blog", "vuln mgmt"),
    ("Mandiant", "mandiant.com/resources/blog", "IR/CTI"),
    ("CrowdStrike", "crowdstrike.com/blog", "CTI"),
    ("Securelist", "securelist.com", "Kaspersky research"),
    ("Krebs on Security", "krebsonsecurity.com", "investigative"),
    ("Schneier on Security", "schneier.com", "analysis"),
    ("Troy Hunt", "troyhunt.com", "breaches / HIBP"),
    ("The Hacker News", "thehackernews.com", "news"),
    ("Dark Reading", "darkreading.com", "news"),
    ("SecurityWeek", "securityweek.com", "news"),
    ("Help Net Security", "helpnetsecurity.com", "news"),
    ("Infosecurity Magazine", "infosecurity-magazine.com", "news"),
    ("CyberScoop", "cyberscoop.com", "policy/news"),
    ("Risky Business", "risky.biz", "podcast/news"),
    ("The Record", "therecord.media", "news"),
    ("CyberWire", "thecyberwire.com", "daily brief"),
]

# --------------------------------------------------------------------------
# Learning / practice labs
# --------------------------------------------------------------------------
LEARNING = [
    ("PortSwigger Web Security Academy", "portswigger.net/web-security",
     "free, best web-app course + labs"),
    ("TryHackMe", "tryhackme.com", "guided rooms"),
    ("Hack The Box", "hackthebox.com", "labs + academy"),
    ("VulnHub", "vulnhub.com", "downloadable VMs"),
    ("PentesterLab", "pentesterlab.com", "web exercises"),
    ("OverTheWire", "overthewire.org", "wargames"),
    ("picoCTF", "picoctf.org", "beginner CTF"),
    ("pwn.college", "pwn.college", "systems/binary, free"),
    ("Root-Me", "root-me.org", "challenges (FR)"),
    ("HackThisSite", "hackthissite.org", "beginner challenges"),
    ("Exploit Education", "exploit.education", "binary exploitation"),
    ("ROP Emporium", "ropemporium.com", "ROP"),
    ("CryptoHack", "cryptohack.org", "cryptography"),
    ("pwnable.tw", "pwnable.tw", "pwn"),
    ("pwnable.kr", "pwnable.kr", "pwn"),
    ("Microcorruption", "microcorruption.com", "embedded RE"),
    ("CTFtime", "ctftime.org", "CTF calendar + writeups"),
    ("OWASP Juice Shop", "owasp.org/www-project-juice-shop", "vulnerable app"),
    ("DVWA", "dvwa.co.uk", "vulnerable app"),
    ("WebGoat", "owasp.org/www-project-webgoat", "vulnerable app"),
    ("PortSwigger Labs", "portswigger.net/web-security/all-labs", "labs"),
    ("HackTricks", "book.hacktricks.xyz", "technique reference"),
    ("GTFOBins", "gtfobins.github.io", "unix privesc"),
    ("LOLBAS", "lolbas-project.github.io", "windows living-off-the-land"),
    ("PayloadsAllTheThings", "github.com/swisskyrepo/PayloadsAllTheThings",
     "payload reference"),
    ("Blue Team Labs Online", "blueteamlabs.online", "defence labs"),
    ("LetsDefend", "letsdefend.io", "SOC training"),
    ("CyberDefenders", "cyberdefenders.org", "blue-team challenges"),
    ("Malware Traffic Analysis", "malware-traffic-analysis.net", "PCAPs"),
    ("DFIR Training", "dfir.training", "IR resources"),
    ("SANS Cyber Aces", "sans.org/cyberaces", "free fundamentals"),
    ("SANS Free Resources", "sans.org/free", "posters/cheat sheets"),
    ("TCM Security", "tcm-sec.com", "practical courses"),
    ("OffSec", "offsec.com", "OSCP etc."),
    ("INE", "ine.com", "eJPT/CPTS-style"),
    ("Antisyphon", "antisyphon-training.com", "pay-what-you-can"),
    ("Black Hills InfoSec", "blackhillsinfosec.com", "training"),
    ("AppSecEngineer", "appsecengineer.com", "hands-on appsec"),
    ("Zero Point Security", "zeropointsecurity.co.uk", "red team"),
    ("ired.team", "ired.team", "red-team notes"),
    ("Pentester Academy", "pentesteracademy.com", "courses"),
]

# --------------------------------------------------------------------------
# Standards / databases (cite these in reports)
# --------------------------------------------------------------------------
STANDARDS = [
    ("OWASP Top 10", "owasp.org/www-project-top-ten", "web risk baseline"),
    ("OWASP WSTG", "owasp.org/www-project-web-security-testing-guide",
     "testing methodology"),
    ("OWASP ASVS", "owasp.org/www-project-application-security-verification-standard",
     "verification requirements"),
    ("CWE Top 25", "cwe.mitre.org/top25", "root-cause classes"),
    ("MITRE ATT&CK", "attack.mitre.org", "adversary tactics"),
    ("CAPEC", "capec.mitre.org", "attack patterns"),
    ("CVE", "cve.org", "vulnerability ids"),
    ("NVD", "nvd.nist.gov", "CVSS + CPE data"),
    ("CVSS", "first.org/cvss", "severity scoring"),
    ("CISA KEV", "cisa.gov/known-exploited-vulnerabilities-catalog",
     "exploited in the wild"),
    ("Exploit-DB", "exploit-db.com", "public exploits"),
    ("Vulners", "vulners.com", "vuln search"),
    ("VulDB", "vuldb.com", "vuln database"),
    ("Have I Been Pwned", "haveibeenpwned.com", "breach lookup"),
    ("crt.sh", "crt.sh", "certificate transparency"),
    ("Shodan", "shodan.io", "internet-wide scan data"),
    ("Censys", "censys.io", "internet-wide scan data"),
    ("VirusTotal", "virustotal.com", "file/URL analysis"),
    ("urlscan.io", "urlscan.io", "URL sandbox"),
    ("SecurityTrails", "securitytrails.com", "DNS/history"),
]

# --------------------------------------------------------------------------
# Tooling, grouped by job
# --------------------------------------------------------------------------
TOOLS = [
    ("Burp Suite", "portswigger.net/burp", "web proxy (Community free)"),
    ("ZAP", "zaproxy.org", "open-source web proxy"),
    ("Caido", "caido.io", "modern web proxy"),
    ("mitmproxy", "mitmproxy.org", "scriptable proxy"),
    ("nmap", "nmap.org", "port/service scan"),
    ("masscan", "github.com/robertdavidgraham/masscan", "fast scan"),
    ("amass", "github.com/owasp-amass/amass", "asset discovery"),
    ("subfinder", "github.com/projectdiscovery/subfinder", "subdomain enum"),
    ("assetfinder", "github.com/tomnomnom/assetfinder", "subdomain enum"),
    ("httpx", "github.com/projectdiscovery/httpx", "HTTP probe"),
    ("dnsx", "github.com/projectdiscovery/dnsx", "DNS toolkit"),
    ("naabu", "github.com/projectdiscovery/naabu", "port scan"),
    ("katana", "github.com/projectdiscovery/katana", "crawler"),
    ("gau", "github.com/lc/gau", "URL discovery"),
    ("waybackurls", "github.com/tomnomnom/waybackurls", "archive URLs"),
    ("ffuf", "github.com/ffuf/ffuf", "fuzzing"),
    ("gobuster", "github.com/OJ/gobuster", "content discovery"),
    ("feroxbuster", "github.com/epi052/feroxbuster", "content discovery"),
    ("dirsearch", "github.com/maurosoria/dirsearch", "content discovery"),
    ("nuclei", "github.com/projectdiscovery/nuclei", "template scanning"),
    ("nikto", "github.com/sullo/nikto", "web server scan"),
    ("sqlmap", "sqlmap.org", "SQLi detection"),
    ("hydra", "github.com/vanhauser-thc/thc-hydra", "credential testing"),
    ("John the Ripper", "openwall.com/john", "password cracking"),
    ("hashcat", "hashcat.net", "GPU cracking"),
    ("Metasploit", "metasploit.com", "exploit framework"),
    ("Sliver", "github.com/BishopFox/sliver", "C2 (authorised red team)"),
    ("BloodHound", "github.com/SpecterOps/BloodHound", "AD attack paths"),
    ("Impacket", "github.com/fortra/impacket", "network protocol toolkit"),
    ("Responder", "github.com/lgandx/Responder", "LLMNR/NBT-NS"),
    ("Ghidra", "ghidra-sre.org", "reverse engineering"),
    ("IDA", "hex-rays.com/ida-pro", "reverse engineering (commercial)"),
    ("Binary Ninja", "binary.ninja", "reverse engineering (commercial)"),
    ("radare2", "rada.re", "reverse engineering"),
    ("AFL++", "github.com/AFLplusplus/AFLplusplus", "fuzzing"),
    ("libFuzzer", "llvm.org/docs/LibFuzzer", "in-process fuzzing"),
    ("honggfuzz", "github.com/google/honggfuzz", "fuzzing"),
    ("OSS-Fuzz", "github.com/google/oss-fuzz", "continuous fuzzing"),
    ("Semgrep", "semgrep.dev", "SAST"),
    ("CodeQL", "codeql.github.com", "SAST (semantic)"),
    ("Bandit", "github.com/PyCQA/bandit", "Python SAST"),
    ("gosec", "github.com/securego/gosec", "Go SAST"),
    ("Brakeman", "brakemanscanner.org", "Rails SAST"),
    ("Trivy", "github.com/aquasecurity/trivy", "container/deps"),
    ("Grype", "github.com/anchore/grype", "vuln scanning"),
    ("Syft", "github.com/anchore/syft", "SBOM"),
    ("Wireshark", "wireshark.org", "packet analysis"),
    ("tcpdump", "tcpdump.org", "packet capture"),
]

# --------------------------------------------------------------------------
# Conferences
# --------------------------------------------------------------------------
CONFERENCES = [
    ("DEF CON", "defcon.org", "largest hacker con"),
    ("Black Hat", "blackhat.com", "industry + research"),
    ("RSA Conference", "rsaconference.com", "enterprise"),
    ("BSides", "securitybsides.com", "local, many cities"),
    ("OWASP Global AppSec", "owasp.org/events", "appsec"),
    ("Pwn2Own (conference)", "zerodayinitiative.com/pwn2own",
     "exploit contest"),
    ("HITB", "conference.hitb.org", "Asia/EU"),
    ("Nullcon", "nullcon.net", "India"),
    ("TROOPERS", "troopers.de", "Germany"),
    ("CanSecWest", "cansecwest.com", "Canada"),
    ("SecTor", "sector.ca", "Canada"),
    ("Infosecurity Europe", "infosecurityeurope.com", "UK"),
    ("BlueHat", "microsoft.com/bluehat", "Microsoft"),
    ("Hexacon", "hexacon.fr", "France"),
    ("OffensiveCon", "offensivecon.org", "Berlin"),
    ("REcon", "recon.cx", "reverse engineering"),
    ("TyphoonCon", "typhooncon.com", "exploit dev"),
]

ALL = (PLATFORMS + VDP + FORUMS + LEARNING + STANDARDS + TOOLS + CONFERENCES)

# --------------------------------------------------------------------------
# Method: the short version, authorisation first
# --------------------------------------------------------------------------
METHOD = {
    "rules": [
        "Only test targets that are explicitly in scope in a programme policy "
        "or that you own. 'Public' is not permission.",
        "Read the policy: scope, out-of-scope, rate limits, prohibited tests, "
        "disclosure rules, safe-harbour language.",
        "Never touch real user data. Use your own accounts and test data.",
        "Stop and report if you reach production data or a critical system.",
        "Follow the programme's disclosure timeline. Do not publish early.",
    ],
    "recon": [
        "Map the attack surface: subdomains, ports, technologies, APIs.",
        "Passive first (CT logs, archives, DNS history) before active scans.",
        "Look for forgotten assets: staging, old APIs, mobile endpoints, "
        "third-party integrations.",
        "Read the app as a user, then as an attacker: what is trusted?",
    ],
    "bug_classes": [
        ("Broken access control / IDOR", "change an id or role and see if the "
         "server still enforces ownership"),
        ("Injection", "SQLi, NoSQLi, command, template, LDAP -- user input "
         "reaching an interpreter"),
        ("SSRF", "server-side fetch of a user-supplied URL"),
        ("Authentication / session", "token handling, MFA bypass, reset flows"),
        ("Deserialisation", "untrusted data into a parser that executes"),
        ("Race conditions", "TOCTOU on balance, coupon, or one-time actions"),
        ("Business logic", "price, quantity, negative values, step skipping"),
        ("XSS / CSRF", "client-side execution and state-changing requests"),
        ("Information disclosure", "debug endpoints, stack traces, backups"),
        ("Cryptographic flaws", "weak randomness, ECB, missing verification"),
    ],
    "reporting": [
        "Title: impact first, one line.",
        "Steps to reproduce: numbered, exact, minimal.",
        "Proof of concept: request/response or script, no real user data.",
        "Impact: what an attacker gains, and who is affected.",
        "Severity: CVSS vector plus a plain-language justification.",
        "Remediation: a concrete fix, not 'sanitise input'.",
    ],
    "finding_bugs_in_code": [
        "Trace untrusted input to a sink (query, exec, file, network).",
        "Check every authorisation decision on the server, never the client.",
        "Look for secrets in history, config, and build artefacts.",
        "Fuzz parsers and decoders with structure-aware inputs.",
        "Run SAST (Semgrep/CodeQL) then manually confirm each hit.",
    ],
}


# --------------------------------------------------------------------------
# Query surface
# --------------------------------------------------------------------------
def _fmt(rows, limit=40):
    out = []
    for name, url, note in rows[:limit]:
        out.append(f"- {name} -- {url}" + (f" ({note})" if note else ""))
    if len(rows) > limit:
        out.append(f"... and {len(rows) - limit} more")
    return "\n".join(out)


def kb_search(query: str = "", kind: str = "", limit: int = 40) -> str:
    """Search the reference list by name/note/domain, optionally by kind."""
    q = (query or "").strip().lower()
    k = (kind or "").strip().lower()

    buckets = {
        "platform": PLATFORMS,
        "vdp": VDP,
        "forum": FORUMS,
        "learning": LEARNING,
        "standard": STANDARDS,
        "tool": TOOLS,
        "conference": CONFERENCES,
    }
    if k and k in buckets:
        rows = buckets[k]
        if q:
            rows = [r for r in rows
                    if q in r[0].lower() or q in r[1].lower()
                    or q in (r[2] or "").lower()]
        head = f"{k} ({len(rows)} match{'es' if len(rows) != 1 else ''})"
        return head + "\n" + (_fmt(sorted(rows), limit) if rows else "(none)")

    if q:
        hits = [r for r in ALL
                if q in r[0].lower() or q in r[1].lower()
                or q in (r[2] or "").lower()]
    else:
        hits = ALL
    if not hits:
        return f"no entry matches {query!r}"

    # group by original bucket, preserving order
    lines = [f"{len(hits)} match{'es' if len(hits) != 1 else ''} for "
             f"{query!r}" if query else f"{len(ALL)} entries"]
    seen = set()
    for label, rows in (("platforms", PLATFORMS), ("vendor/VDP", VDP),
                        ("forums", FORUMS), ("learning", LEARNING),
                        ("standards", STANDARDS), ("tools", TOOLS),
                        ("conferences", CONFERENCES)):
        sub = [r for r in rows if r in hits]
        if not sub:
            continue
        take = sub[:limit]
        seen.update(r[0] for r in take)
        lines.append(f"\n[{label}]")
        lines.append(_fmt(sorted(take), limit))
        limit -= len(take)
        if limit <= 0:
            break
    return "\n".join(lines)


def kb_counts() -> str:
    return (f"platforms={len(PLATFORMS)} vdp={len(VDP)} forums={len(FORUMS)} "
            f"learning={len(LEARNING)} standards={len(STANDARDS)} "
            f"tools={len(TOOLS)} conferences={len(CONFERENCES)} "
            f"total={len(ALL)}")


def kb_topic(topic: str = "") -> str:
    """Return the short methodology for a topic."""
    t = (topic or "").strip().lower()
    if not t:
        return ("topics: " + ", ".join(METHOD))
    if t in ("authorisation", "authorization", "scope", "rules", "policy"):
        key = "rules"
    elif t in ("recon", "reconnaissance", "enumeration"):
        key = "recon"
    elif t in ("bug", "bugs", "bug_classes", "classes", "vulns",
               "vulnerabilities"):
        key = "bug_classes"
    elif t in ("report", "reporting", "writeup", "disclosure"):
        key = "reporting"
    elif t in ("code", "sast", "review", "source", "bugfinding"):
        key = "finding_bugs_in_code"
    else:
        return (f"unknown topic {topic!r}; topics: " + ", ".join(METHOD))

    body = METHOD[key]
    if isinstance(body[0], tuple):
        lines = [f"- {a}: {b}" for a, b in body]
    else:
        lines = [f"- {x}" for x in body]
    return f"## {key}\n" + "\n".join(lines)


# --------------------------------------------------------------------------
# Tool handlers
# --------------------------------------------------------------------------
def security_kb(args, ctx):
    """Search bug-bounty platforms, forums, labs, standards and tools."""
    q = (args.get("query") or "").strip()
    kind = (args.get("kind") or "").strip()
    try:
        limit = int(args.get("limit") or 40)
    except Exception:
        limit = 40
    limit = max(1, min(limit, 200))
    body = kb_search(q, kind, limit)
    return {"ok": True, "output": body + "\n\n" + kb_counts(),
            "text": body + "\n\n" + kb_counts()}


def security_method(args, ctx):
    """Short, authorisation-first methodology for a security topic."""
    topic = (args.get("topic") or "").strip()
    body = kb_topic(topic)
    return {"ok": True, "output": body, "text": body}
