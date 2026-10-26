# Incident notes: npm worm and account-takeover incidents (Aug to Nov 2025)

Empirical facts for calibrating the SIR model of npm supply-chain worms. Every fact below gives its source URL and that source's publication date. "Derived" means we computed the figure ourselves from `data/raw/incidents/compromised_packages.csv`, joined with npm registry metadata.

Retrieval date for all sources: 2026-10-26. Raw copies are in `data/raw/incidents/sources/`.

## 0. Dataset: `data/raw/incidents/compromised_packages.csv`

Columns: `package,version,incident,first_seen_utc,maintainer_account,source_url`. Each row is one package@version within one incident.

| incident tag | rows (package@version) | distinct packages | sources merged |
|---|---|---|---|
| `shai-hulud-1` | 593 | 203 | StepSecurity, Socket, Endor Labs, Aikido, Semgrep, JFrog, Wiz (7 vendor lists) |
| `shai-hulud-2` | 1091 | 795 | Wiz IOC CSV, Datadog IOC CSV, Datadog consolidated CSV (Koi, StepSecurity, Aikido, Wiz, ReversingLabs, HelixGuard, Socket, Datadog) |
| `context-chalk-debug-qix` | 25 | 24 | Aikido, Socket, Wiz, DuckDB GHSA |
| `context-s1ngularity-nx` | 19 | 8 | Nx GHSA-cxm3-wv7p-598c |

How the columns were filled:
- **`first_seen_utc`**: the npm registry publish timestamp, taken from the packument `time` map at `https://registry.npmjs.org/<pkg>`. npm keeps that map even after it removes the malicious versions. Raw extract: `sources/npm_registry_metadata_extract.jsonl`.
  - When we used the registry, its URL is appended to `source_url`.
  - For the 61 rows whose package now returns 404, the value falls back to the date-only "Published (UTC)" from Endor Labs, or is blank.
  - Breakdown of the 61 blank or date-only rows: 58 in SH2, 2 in SH1, 1 in chalk.
  - No tarballs were downloaded and nothing was installed.
- **`maintainer_account`**: filled only when a source names the account.
  - `qix` (Aikido/Socket). Socket and Wiz call the account "Qix"; we write it in npm's lowercase username form.
  - `duckdb_admin` (DuckDB GHSA).
  - `crowdstrike-publisher` (Socket, for `@crowdstrike/*`).
  - All other cells are blank. No source names the compromised npm account for the SH1/SH2 packages.
- **Deduplication**: `source_url` keeps every source that listed the row, separated by `;`.
- **Coverage**: the 4 incidents share no package@version and no package name.

### Source disagreements (recorded, not resolved by guessing)

**Shai-Hulud 1**

Agreement across sources. Of 593 versions:
- 263 are listed by all 7 sources and 184 by 6.
- 39 appear in only one source:
  - Endor Labs only: 32. These are mostly prerelease or extra versions of `@tnf-dev/*`, `@art-ws/*` and `@thangved/callback-window`, plus `mcfly-semantic-release@1.3.4`.
  - Socket only: 4.
  - JFrog only: 2 (`react-jsonschema-rxnt-extras@0.4.6`, `@0.4.7`).
  - Wiz only: 1.

Four listed versions were published long before the incident, according to npm registry timestamps. They are probably false positives or typos in the source list. They are kept in the CSV but should be excluded from timing fits:
- `@nativescript-community/ui-document-picker@13.0.32`, published 2021-12-03 (Wiz only).
- `@rxap/ngx-bootstrap@19.0.3` and `@19.0.4`, published 2025-03-07 and 2025-05-16 (Socket only). Wiz and others list the unscoped `ngx-bootstrap` at these version numbers instead.
- `@teriyakibomb/ember-velcro@2.2.1`, published 2025-08-31 (Socket only). It is still listed on npm.

Other SH1 disagreements:
- **Earliest malicious version.**
  - Socket says `rxnt-authentication@0.0.3` at 17:58:50 UTC on 2025-09-14, and the registry agrees (17:58:50.315Z).
  - Endor Labs says the earliest was `airpilot@0.8.8` at 2025-09-14T18:35:07Z.
- **`another-shai@1.0.1`** (2025-09-17 17:00 UTC) is listed only by Socket. It may be a copycat.
- **Semgrep ranges.** Semgrep lists version ranges such as `2.0.4-2.0.5`. Only the two endpoints were recorded.
- **Headline counts.**

  | source | headline count |
  |---|---|
  | StepSecurity | "500+ packages" |
  | Socket | "nearly 500" packages, with a list of 526 package@versions |
  | Endor Labs | 582 versions / 194 packages |
  | Aikido | 187 packages |
  | Semgrep | 187+ packages |
  | JFrog (day 1) | 164 packages / 338 versions |
  | CISA | "over 500 packages" |
  | GitHub | "500+ compromised packages" removed |

  The "500+" figures match the number of package versions (about 590 in our union), not the number of distinct packages (about 200). JFrog's November update also says the first wave had "1,150+" packages, which no other source supports.

**Shai-Hulud 2**
- Wiz and Datadog consolidated agree on 795 package names.
- Datadog's own list has 2 versions that appear in neither of the other files.
- Datadog removed 3 HelixGuard entries as false positives: `cbre-flow-common`, `@elsedev/react-csr-sdk`, `utilitas`.
- Wiz says the packages "were uploaded to npm between November 21-23, 2025". The npm registry timestamps put every timed malicious version between 2025-11-24 03:10:05Z and 17:54:20Z.
- StepSecurity's post is dated November 23, 2025, which probably reflects a US timezone.

**chalk/debug**
- `proto-tinker-wc` is listed as `0.1.87` by Wiz and by Socket's own timeline, but as `1.8.7` in Socket's IOC list. The registry has no record of 1.8.7, and 0.1.87 was published 2025-09-08. Both rows are kept; 1.8.7 has a blank timestamp.
- Wiz alone adds `@coveops/abi@2.0.1` and the four DuckDB packages. The DuckDB packages are confirmed by DuckDB's own advisory.

## 1. Timelines

### 1a. s1ngularity / Nx (context), 2025-08-26

All times are converted to UTC. The Nx advisory gives times in EDT (UTC-4).

| time (UTC) | event | source |
|---|---|---|
| 2025-08-24 20:50 | Attacker commit exfiltrates the Nx npm publish token through a `pull_request_target` workflow injection | Nx GHSA, https://github.com/nrwl/nx/security/advisories/GHSA-cxm3-wv7p-598c (published 2025-08-27) |
| 2025-08-26 22:31:44 | First malicious publish (`@nx/devkit@21.5.0`); registry shows 13 versions within 1 h | npm registry; Nx GHSA ("6:32 PM EDT") |
| 2025-08-27 00:30 | First public report (GitHub issue nrwl/nx#32522), **+2.0 h** | Nx GHSA |
| 2025-08-27 00:37 | Last malicious publish (`nx@20.12.0`); 19 versions in total | npm registry |
| 2025-08-27 02:44 | npm removes affected versions and all publish tokens, **+4.2 h** | Nx GHSA |
| 2025-08-27 09:00 | GitHub disables attacker-created repos after an exposure window of about 8 h | Wiz, https://www.wiz.io/blog/s1ngularity-supply-chain-attack (2025-08-27, updated 2025-08-29) |
| 2025-08-27 15:57 | All Nx packages require 2FA and switch to trusted publishing | Nx GHSA |
| 2025-08-28 16:00 to 08-29 02:00 | Phase 2: stolen GitHub tokens used to make private repos public. Over 400 users/orgs and over 5,500 repos affected | Wiz (2025-08-27, updated 2025-08-29) |

### 1b. chalk/debug "qix" phishing takeover (context), 2025-09-08

| time (UTC) | event | source |
|---|---|---|
| 2025-09-08 13:12:10 | First malicious publish (`ansi-styles@6.2.2`); 18 qix packages within 1 h | npm registry; Socket, https://socket.dev/blog/npm-author-qix-compromised-in-major-supply-chain-attack (2025-09-08): "01:12–01:16 PM" first wave, "01:19–01:20 PM" second wave |
| 2025-09-08 13:16 | Aikido intel feed alerts, **about +4 min** | Aikido, https://www.aikido.dev/blog/npm-debug-and-chalk-packages-compromised (2025-09-08) |
| about 2025-09-08 15:00 | Maintainer acknowledges and starts removal (Wiz says "around 11AM EST"); versions "removed from npm a few hours later". Wiz gives the exposure window as "13:16–~15:15 UTC" | Wiz, https://www.wiz.io/blog/widespread-npm-supply-chain-attack-breaking-down-impact-scope-across-debug-chalk (2025-09-09) |
| 2025-09-09 01:11 to 01:26 | Same phishing campaign hits `duckdb_admin` (4 DuckDB packages) and `@coveops/abi` | npm registry; DuckDB GHSA, https://github.com/duckdb/duckdb-node/security/advisories/GHSA-w62p-hx95-gf2c (2025-09-09) |

### 1c. Shai-Hulud (wave 1), 2025-09-14 to 09-16

| time (UTC) | event | source |
|---|---|---|
| 2025-09-14 17:58:50 | **First malicious publish** (`rxnt-authentication@0.0.3`) | npm registry; Socket, https://socket.dev/blog/ongoing-supply-chain-attack-targets-crowdstrike-npm-packages (2025-09-16), "17:58 first observed compromise" |
| 2025-09-14 | GitHub states "On September 14, 2025, we were notified of the Shai-Hulud attack" (date only) | GitHub, https://github.blog/security/supply-chain-security/our-plan-for-a-more-secure-npm-supply-chain/ (2025-09-22) |
| 2025-09-14 18:35, 20:29–20:45, 21:01–21:03; 09-15 01:12, 02:11, … | Burst timestamps (see Socket's full list) | Socket (2025-09-16) |
| 2025-09-15 19:52:46 | `@ctrl/tinycolor@4.1.1` published, the package that drew attention | npm registry; JFrog, https://jfrog.com/blog/shai-hulud-npm-supply-chain-attack-new-compromised-packages-detected/ (2025-09-16, updated 2025-11-24) |
| 2025-09-15 about 18:11 | "Early posts on social media about suspicious activity", **about +24.2 h** after the first publish | Semgrep, https://semgrep.dev/blog/2025/security-advisory-npm-packages-using-secret-scanning-tools-to-steal-credentials/ (2025-09-15). Semgrep writes "11:11am PDT (06:41pm UTC)"; 11:11 PDT is 18:11 UTC, so its UTC conversions are inconsistent |
| 2025-09-15 about 22:45 | Report filed at scttcper/tinycolor#256 (Semgrep: "3:45pm PDT") | Semgrep |
| 2025-09-15 by 23:23 | Socket's first blog post (tinycolor, 40+ packages); StepSecurity's post is dated 2025-09-15 | Semgrep; StepSecurity, https://www.stepsecurity.io/blog/ctrl-tinycolor-and-40-npm-packages-compromised (2025-09-15) |
| 2025-09-16 01:14 | Largest single burst, "nearly 100 packages" (CrowdStrike set) | Socket |
| 2025-09-16 11:44 | Last burst (`@operato`, `@things-factory`); 99% of timed versions published by 11:43 (derived) | npm registry; Socket ("10:57–11:09 more @operato") |
| by 2025-09-22 | npm removed "500+ compromised packages" and is "blocking the upload of new packages containing the malware's IoCs ... cutting off the self-replicating pattern" | GitHub (2025-09-22) |
| 2025-09-23 | CISA alert: "over 500 packages"; pin to releases "prior to Sept. 16, 2025" | CISA, https://www.cisa.gov/news-events/alerts/2025/09/23/widespread-supply-chain-compromise-impacting-npm-ecosystem (2025-09-23) |
| as of update (page updated 2025-09-25) | 582 versions, 47 still available on npm, 194 packages | Endor Labs, https://www.endorlabs.com/learn/npm-malware-outbreak-tinycolor-and-crowdstrike-packages-compromised (2025-09-16, updated 2025-09-25) |

Compromised SH1 packages over time (derived). The counts exclude the 4 pre-incident rows and the 3 untimed rows.
- **Hours after the first publish (t0 = 2025-09-14 17:58:50Z):**

  | hours after t0 | packages | versions |
  |---|---|---|
  | 1 | 15 | 15 |
  | 3 | 36 | 47 |
  | 6 | 54 | 76 |
  | 12 | 82 | 118 |
  | 18 | 120 | 224 |
  | 24 | 126 | 256 |
  | 30 | 173 | 340 |
  | 36 | 197 | 483 |
  | 42 | 197 | 585 |
  | 72 | 198 | 586 (adds `another-shai`) |

- **Milestones:** 50% of versions by +26.2 h, 90% by +37.1 h, 99% by +41.7 h.
- **By UTC calendar day:**

  | UTC day | new packages | cumulative packages | versions published that day |
  |---|---|---|---|
  | 2025-09-14 | 54 | 54 | 76 |
  | 2025-09-15 | 119 | 173 | 264 |
  | 2025-09-16 | 24 | 197 | 245 |
  | 2025-09-17 | 1 | 198 | 1 |

  The Endor Labs table gives the same daily split by date: 73 / 264 / 245 versions.
- **Versions per UTC hour** (from 09-14 17h): 9, 6, –, 32, 29, … The largest hour was 09-16 01h with 81 versions. The full series can be recomputed from the CSV.

### 1d. Shai-Hulud 2.0 / "Sha1-Hulud: The Second Coming", 2025-11-24

| time (UTC) | event | source |
|---|---|---|
| 2025-11-24 01:22 | Earliest GitHub exfiltration repos (GH Archive), before any npm publish | Wiz, https://www.wiz.io/blog/shai-hulud-2-0-ongoing-supply-chain-attack (2025-11-24, updates to 11-27) |
| 2025-11-24 03:10:05 | **First malicious publish** (`@asyncapi/avro-schema-parser@3.0.25`); 36 AsyncAPI packages plus `go-template` | npm registry; Wiz: "~03:00 UTC"; Aikido: first detected "3:16:26 AM GMT+0" |
| 2025-11-24 03:16:26 | Aikido detects the first packages, **+6 min** | Aikido, https://www.aikido.dev/blog/shai-hulud-strikes-again-hitting-zapier-ensdomains (2025-11-24) |
| 2025-11-24 04:11:55 / 05:09:25 | PostHog packages, then Postman packages, compromised | Aikido (2025-11-24) |
| 2025-11-24 (same day) | Public write-ups from Aikido, Wiz, StepSecurity and Koi. StepSecurity's page is dated 11-23 and reports "Over 70 npm packages" at writing | StepSecurity, https://www.stepsecurity.io/blog/sha1-hulud-the-second-coming-zapier-ens-domains-and-other-prominent-npm-packages-compromised |
| 2025-11-24 17:54:20 | **Last malicious publish** in the timed data. Datadog: "The last affected package we have witnessed was published at 6 p.m. UTC on November 24, indicating that npm may have taken measures to prevent further packages from being backdoored" | npm registry; Datadog, https://securitylabs.datadoghq.com/articles/shai-hulud-2.0-npm-worm/ (2025-11-25, updated 2025-12-04) |
| 2025-11-24 19:00 | Cross-victim exfiltration confirmed | Wiz |
| 2025-11-25 22:45 | Possible second phase: an initial victim's private repos published | Wiz |
| 2025-11-26 about 09:00 | GitHub begins removing repos, revoking leaked tokens and notifying users. Public repos fall to about 300 on 11-26 | Wiz |
| 2025-11-26 16:00 | Abuse of leaked AWS keys and GitHub PATs observed | Wiz |
| 2025-11-27 11:00 | "only ~15 malicious package versions remain available on npm" | Wiz |

Compromised SH2 packages over time (derived from 1,033 timed versions / 749 packages; 46 packages are untimed because they now return 404):
- **Hours after the first publish (t0 = 03:10:05Z):**

  | hours after t0 | packages | versions |
  |---|---|---|
  | 1 | 126 | 171 |
  | 2 | 165 | 212 |
  | 3 | 266 | 359 |
  | 6 | 331 | 462 |
  | 12 | 613 | 889 |
  | 14.7 | 749 | 1033 (complete) |

- **Milestones:** 50% of versions by +6.9 h, 90% by +13.4 h, 99% by +13.7 h.
- **Versions per UTC hour on 11-24:**

  | hour (UTC) | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 |
  |---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
  | versions | 105 | 91 | 147 | 62 | 52 | 4 | 41 | 208 | 139 | 21 | 12 | 7 | 27 | 106 | 11 |

- **Vendor running counts:**
  - StepSecurity: "Over 70" packages at writing.
  - Wiz: "~700", then "nearly 800" packages.
  - Datadog: 796 packages.
  - JFrog: 796 packages (JFrog, updated 2025-11-24).

## 2. Propagation mechanism

| aspect | Shai-Hulud 1 (Sep 2025) | Shai-Hulud 2.0 (Nov 2025) |
|---|---|---|
| Install hook | `postinstall` running `node bundle.js` (StepSecurity 2025-09-15; Wiz 2025-09-16; Semgrep 2025-09-15). GitHub: "injecting malicious post-install scripts" (2025-09-22) | `preinstall` running `node setup_bun.js`. It installs Bun, then runs `bun_environment.js`, a payload of 10 MB or more (StepSecurity; Wiz; Datadog 2025-11-25). Wiz: "This variant executes only during the preinstall phase" |
| Needs install scripts to run? | Yes. The payload runs only through the lifecycle hook; Semgrep recommends `--ignore-scripts` as mitigation | Yes. Preinstall runs before the install finishes, so it fires even when the install later fails (Aikido; Wiz) |
| Token theft | Dumps `process.env` (`NPM_TOKEN`, `GITHUB_TOKEN`, AWS keys) and runs `trufflehog filesystem /`. Reads `NPM_TOKEN` from `~/.npmrc` or environment variables and validates it via `/whoami`. Also collects cloud metadata and AWS/GCP secret managers (StepSecurity 2025-09-15; Socket 2025-09-16) | Reads environment variables, `~/.npmrc` (current directory or home), GitHub token (`GITHUB_TOKEN`/`~/.netrc`), TruffleHog, cloud SDKs and IMDS (StepSecurity; Datadog; Wiz) |
| Which packages it republishes | Queries `/v1/search?text=maintainer:${username}&size=20`, so **up to 20 packages per stolen token**. It bumps the patch version and runs `npm publish` (StepSecurity 2025-09-15). Socket: "In Version 4, the tool attempts to iterate up to 20 packages of a single maintainer instead of 10", so early versions capped at **10** (Socket 2025-09-16) | Calls `/-/v1/search` for the token owner's packages and backdoors **the first 100** (Datadog 2025-11-25; Aikido: "up to 100 npm packages, compared to 20 last time") |
| Number of worm builds | 7 distinct bundle versions with "multiple different seeder events" (Socket 2025-09-16) | – |
| GitHub exfiltration and persistence | Public repo named `Shai-Hulud` holding stolen secrets. Pushes `.github/workflows/shai-hulud-workflow.yml` that sends `toJSON(secrets)` to a webhook. A "migration" routine republishes private repos publicly with a `-migration` suffix (StepSecurity; Wiz 2025-09-16) | Public repo with a random name and description "Sha1-Hulud: The Second Coming". If it has no GitHub token, it searches for other victims' exfiltration repos and uses their tokens ("cross-victim"). Registers a self-hosted runner named `SHA1HULUD` and a `discussion.yaml` workflow that is vulnerable to injection, a backdoor. Exfiltrates secrets through `formatter_*.yml`. Wipes the home directory if it can neither authenticate nor exfiltrate (Datadog; Wiz; StepSecurity; Aikido) |
| Platforms | Skips Windows; checks for linux/darwin (StepSecurity) | Linux, Windows and macOS runners (Wiz) |
| Seed / initial access | Wiz: "initial npm packages that started this chain reaction included multiple known-compromised victims of the s1ngularity" attack (Wiz 2025-09-16) | AsyncAPI: a malicious branch of the CLI repo "created just prior to the malicious packages being pushed" (Aikido 2025-11-24). GitHub exfiltration repos appeared at 01:22 UTC, before the first npm publish (Wiz) |

Context incidents:
- **Nx.** A `postinstall` script (`telemetry.js`) harvested credentials, used AI CLIs for reconnaissance, and created `s1ngularity-repository` repos (Wiz 2025-08-27). It had no self-propagation; npm publishing used the one stolen Nx token (Nx GHSA).
- **chalk/debug.** No install script. The code was a browser-side crypto-wallet hijacker that ran when bundled into web apps, and it did not self-propagate (Aikido 2025-09-08; Wiz 2025-09-09).

## 3. Scale

| metric | value | source |
|---|---|---|
| SH1 packages / versions | 203 packages / 593 versions (union), or about 198 / 586 after excluding suspect rows | derived |
| SH1 vendor headline | "500+ packages" (StepSecurity title); "over 500" (CISA); 582 versions / 194 packages (Endor) | see above |
| SH1 weekly downloads | `@ctrl/tinycolor` over 2 M/week (StepSecurity 2025-09-15); over 8 M monthly (Semgrep 2025-09-15). **No aggregate figure found** | – |
| SH1 GitHub repos | "hundreds of such public repositories" (StepSecurity 2025-09-15); "nearly 700 public repositories titled 'Shai-Hulud Migration'" (Socket 2025-09-16) | – |
| SH1 named accounts | `crowdstrike-publisher` (Socket 2025-09-16). No source gives a total count of compromised maintainer accounts | – |
| SH2 packages / versions | 795 packages / 1,091 versions (union) | derived; Wiz CSV; Datadog |
| SH2 weekly downloads | "796 unique npm packages ... total over 20 million weekly downloads" | Datadog (2025-11-25) |
| SH2 prevalence | affected packages present in "roughly 27 % of cloud and code environments" | Wiz (2025-11-24) |
| SH2 dependency reach | "out of nearly 800 affected packages, only ~230 have any direct or indirect dependencies, with only 18 of these having 100 or more" | Wiz (2025-11-24) |
| SH2 GitHub repos | "25,000+ malicious repos across ~500 GitHub users" (Wiz body) vs "~350 unique users" (Wiz subtitle; Unit 42, https://unit42.paloaltonetworks.com/npm-supply-chain-attack/, updated 2025-11-25/26); "~1,000 new repos every 30 minutes" (Wiz); 26.3k repos (Aikido); "22,000+" (StepSecurity); 775 compromised GitHub access tokens in a sample of about 20k repos (Wiz) | – |
| chalk/debug | 18 qix packages, "more than 2 billion downloads per week" (Aikido); "2-3 billion" (Socket); malicious code found in at least 10% of cloud environments (Wiz 2025-09-09) | – |
| Nx | 8 packages / 19 versions; over 1,000 valid GitHub tokens leaked; phase 2: over 5,500 private repos made public across over 400 users/orgs | Nx GHSA; Wiz (2025-08-27) |

## 4. Maintainer-level structure (derived proxies; no source gives this)

No source lists the compromised npm account per package. These two proxies come from the npm registry and are not ground truth.

**(a) Publish bursts** are groups of versions published less than 60 s apart. Under the worm's code, one burst corresponds to one stolen token republishing its owner's packages.

| wave | bursts | packages per burst, mean / median | maximum | notes |
|---|---|---|---|---|
| SH1 | 68 | 8.5 / 8 | 20 | 10 bursts of exactly 20 packages and 15 of exactly 9, matching the 20-package cap (and the earlier 10-package cap) |
| SH2 | 98 | 10.0 / 3 | 98 | 32 single-package bursts; heavy tail of 68, 71, 72, 84, 98 |

With a 120 s gap: SH1 has 63 bursts and SH2 has 81. With 300 s: 49 and 49.

**(b) Clusters of packages sharing a current maintainer.** These use the registry `maintainers` field after remediation, so they include co-maintainers and later changes. A cluster sets an upper limit on the packages behind one account, and the number of clusters is a rough minimum for the number of accounts.

| wave | packages with metadata | current maintainer accounts | clusters | cluster sizes | single-maintainer packages |
|---|---|---|---|---|---|
| SH1 | 189 | 62 | 19 | median 6, mean 10; largest 29, 22, 21, 21, 20, 20, 11, … | 87, held by 14 accounts. Package counts per account include 20, 20, 11, 8, 6, 6, 5 |
| SH2 | 732 | 248 | 88 | median 2, mean 8.3; 34 singletons; largest 103, 71, 62, 49, 46, 36, … | 382, held by 75 accounts. The largest count is 90 packages |

Scopes:
- SH1: 18 scopes plus 80 unscoped packages. Largest scopes: `@nativescript-community` 20, `@art-ws` 15, `@ctrl` 14, `@operato` 13.
- SH2: 71 scopes plus 322 unscoped packages. Largest scopes: `@voiceflow` 57, `@posthog` 56, `@ensdomains` 44, `@oku-ui` 43, `@asyncapi` 36.

## 5. Defensive responses

- **npm response to Shai-Hulud 1.** npm removed 500+ packages and blocked uploads matching the IoCs. GitHub announced plans to allow only:
  - 2FA local publishing;
  - granular tokens with a 7-day lifetime;
  - trusted publishing.

  It also announced plans to deprecate classic tokens and TOTP 2FA, and to disallow tokens by default (GitHub blog, 2025-09-22).
- **Token lifetime.** From mid-October 2025, new write-enabled granular tokens default to 7 days (previously 30) with a 90-day maximum (previously unlimited). Classic tokens were scheduled for revocation in mid-November (GitHub changelog, https://github.blog/changelog/2025-09-29-strengthening-npm-security-important-changes-to-authentication-and-token-management/, 2025-09-29).
- **2025-11-05.** Classic token creation disabled; existing classic tokens work until 2025-11-19. Write tokens enforce 2FA by default, with an opt-in "Bypass 2FA" for CI. Existing write tokens are capped at 90 days (https://github.blog/changelog/2025-11-05-npm-security-update-classic-token-creation-disabled-and-granular-token-changes/, 2025-11-05).
  - Aikido notes that SH2 struck "just before npm's deadline for revoking old tokens" (Aikido 2025-11-24).
- **2025-12-09.** All classic tokens permanently revoked. `npm login` now issues 2-hour session tokens, and 2FA is on by default for new packages (https://github.blog/changelog/2025-12-09-npm-classic-tokens-revoked-session-based-auth-and-cli-token-management-now-available/, 2025-12-09).
- **2025-12-23.** GitHub announces bulk OIDC onboarding for trusted publishing and "staged publishing", which adds a review period with MFA approval before a release goes live (https://github.blog/security/supply-chain-security/strengthening-supply-chain-security-preparing-for-the-next-malware-campaign/, 2025-12-23).
- **pnpm v10.0.0** (released 2025-01-07, before both waves): "Lifecycle scripts of dependencies are not executed during installation by default" unless allow-listed in `onlyBuiltDependencies` (https://github.com/pnpm/pnpm/releases/tag/v10.0.0).
- **Bun**: "does not execute arbitrary lifecycle scripts by default". It runs them only for `trustedDependencies` plus "a curated list of popular npm packages" (https://bun.sh/docs/install/lifecycle, undated docs). Note that SH2 itself installs Bun to run its payload.
- **Did provenance or trusted publishing stop republishing?** (derived; `sources/npm_registry_provenance_extract.jsonl`)
  - **Trusted publishing.** No compromised package had trusted publishing on its last version before the attack: 0/189 for SH1, 0/730 for SH2, 0/8 for Nx. Packages using trusted publishing with tokens disallowed would not have been republishable with a stolen token, but none were hit, so the data cannot test this.
  - **Provenance.** It did not prevent republishing. 15/189 SH1 packages and 3/730 SH2 packages had provenance attestations on their previous version and were still republished with tokens. Nx: "Provenance was attached to recent versions of Nx — This does not prevent installing the package" (Nx GHSA).
  - **After the attacks**, these packages later published versions through trusted publishing: 19/200 SH1, 80/749 SH2, 8/8 Nx.
  - **Caveat:** the `_npmUser.trustedPublisher` field may not mark every older trusted publish.

## 6. Ecosystem adoption estimates

- **Not found in permitted sources**: the fraction of installs using `--ignore-scripts`, pnpm v10, Bun, lockfiles or `npm ci`, and the share of the registry using trusted publishing or provenance. Package-manager survey numbers exist only in secondary or non-vendor sources and were not used.
- **Proxies**:
  - Trusted publishing for npm launched in July 2025 (GitHub blog, 2025-09-22: "npm (also July 2025)"). GitHub's changelog gives general availability as 2025-07-31 (https://github.blog/changelog/2025-07-31-npm-trusted-publishing-with-oidc-is-generally-available/; title and date only, not archived).
  - Among the 981 compromised packages with registry metadata, trusted publishing before the attack was 0%, and provenance was 8% for SH1 and 0.4% for SH2 (derived, section 5). This describes only the attacked population.
  - Wiz prevalence: 99% of cloud environments contained a package targeted in the chalk/debug incident (Wiz 2025-09-09). SH2 packages were present in about 27% of environments (Wiz 2025-11-24).

## 7. Implications for model calibration

1. **Packages per compromised maintainer.**
   - SH1 was capped at 20 per token, and 10 in early builds. Burst sizes have mean 8.5 and median 8, with 10 bursts at exactly 20.
   - SH2 was capped at 100 per token. Burst sizes are heavy-tailed: median 3, mean 10, maximum 98.
   - Use a capped, heavy-tailed offspring distribution, roughly a truncated power law. Use the "packages owned by the maintainer, min(cap, n)" rule, not a fixed number.
2. **Time from first publish to detection.**

   | incident | detection lag |
   |---|---|
   | SH1 | about 24 h to first public signal (2025-09-14 17:58 to about 09-15 18:11 UTC); about 29 h to vendor blogs. Detection came after the high-profile `@ctrl/tinycolor` was hit (09-15 19:52). GitHub says it was notified on 09-14 (time unknown) |
   | SH2 | about 0.1 h to automated vendor detection (Aikido); public reports the same day |
   | Nx | about 2 h |
   | chalk | about 4 min |

3. **Time to plateau.**

   | wave | 90% of versions | last publish | registry blocking |
   |---|---|---|---|
   | SH1 | +37 h | +41.7 h (09-16 11:44 UTC) | blocking of IoC uploads followed |
   | SH2 | +13.4 h | +14.7 h (11-24 17:54 UTC) | Datadog suggests npm intervened |

   Model the outbreak as ending through registry intervention (forced recovery) rather than susceptible depletion.
4. **Dependency installs vs stolen-token republishing.** The evidence favours stolen-token republishing as the mechanism that produces almost all compromised packages:
   - every vendor describes republishing via the maintainer's own token;
   - publish bursts match the per-token caps;
   - Wiz finds only about 230 of about 800 SH2 packages have any dependents.

   Dependency installs (direct, transitive, CI) are the contact route that moves the worm between maintainers. That cross-maintainer chain was short: about 50 to 100 burst events per wave, with several attacker "seeder" events (Socket SH1) and seeding from s1ngularity-stolen tokens (Wiz SH1). Model two layers:
   - a maintainer-level transmission layer (install-triggered token theft), with low per-contact probability that requires an install script to run;
   - an intra-maintainer amplification step, which infects all packages of the token owner up to the cap at once.

## Raw source files

Everything is in `data/raw/incidents/sources/`. Parsing and fetching scripts were kept outside the repo.

| file(s) | source |
|---|---|
| `sh1_*.html` | StepSecurity, Socket, Endor Labs, Wiz, Semgrep, JFrog, Unit 42, Aikido |
| `sh2_*.html` | Wiz, StepSecurity, Aikido, Datadog blog |
| `wiz_shai-hulud-2-packages.csv` | https://github.com/wiz-sec-public/wiz-research-iocs |
| `datadog_sh2_*` | https://github.com/DataDog/indicators-of-compromise/tree/main/shai-hulud-2.0 |
| `chalk_*` | chalk/debug and DuckDB sources |
| `nx_*` | Nx sources |
| `cisa_2025-09-23.html` | CISA alert |
| `github_*` | GitHub blog and changelog posts |
| `pnpm_v10_release_notes.json` | pnpm v10.0.0 release notes |
| `bun_docs_lifecycle.html` | Bun lifecycle-script docs |
| `npm_registry_*_extract.jsonl` | npm registry metadata only; no tarballs |

Not used: a Koi live-updates URL, which now redirects to an unrelated page.
