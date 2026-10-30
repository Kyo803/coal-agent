# Security knowledge base (bug bounty + defensive reference)

Coal carries a curated cybersecurity reference and two tools to query it.
It is deliberately **reference and method, not an exploit kit**.

## What is in it

| category | entries | examples |
|---|---|---|
| bug-bounty platforms | 25 | HackerOne, Bugcrowd, Intigriti, Immunefi, Code4rena |
| vendor / VDP programmes | 23 | Google VRP, MSRC, Apple, GitHub, ZDI |
| forums / communities | 61 | r/netsec, Security StackExchange, SANS ISC, Project Zero |
| learning / practice labs | 41 | PortSwigger Academy, TryHackMe, HTB, pwn.college |
| standards / databases | 20 | OWASP Top 10/WSTG/ASVS, CWE Top 25, ATT&CK, CVE, CVSS |
| tooling | 48 | Burp, ZAP, nuclei, semgrep, CodeQL, AFL++, Ghidra |
| conferences | 17 | DEF CON, Black Hat, BSides, Pwn2Own |
| **total** | **235** | |

## Tools

```
security_kb(query="bounty", kind="platform")   # search the reference
security_kb(kind="learning")                   # list a whole category
security_method(topic="authorisation")         # rules / scope / disclosure
security_method(topic="recon")
security_method(topic="bug_classes")
security_method(topic="reporting")
security_method(topic="code")
```

## The rule it leads with

Every method response starts with authorisation, because the alternative is not
"grey area" — it is a criminal offence in most jurisdictions:

- only targets explicitly in scope in a programme policy, or your own;
- read the policy: scope, prohibited tests, rate limits, disclosure terms;
- never touch real user data;
- follow the disclosure timeline.

The knowledge base exists so the agent can point at **where to learn and who
pays bounties** before it discusses technique.

## Browser control

The agent has 20+ browser tools (Playwright): navigate, snapshot, click, type,
evaluate JS, wait, fill forms, upload, dialogs, console logs, network
requests, screenshots, tabs. That is what makes the security reference
actionable rather than a static document.
