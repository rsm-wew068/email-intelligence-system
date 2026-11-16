# Quantitative NLP & Information Extraction Evaluation Report

**Evaluated Dataset:** [`eval/gold_dataset.json`](gold_dataset.json) (**$N = 55$ held-out corporate emails**, **52 ground-truth deliverables**, **240 entity spans**, zero overlap with UI demo threads)  
**Model Backend:** `gemini-3.5-flash` via Google Cloud Vertex AI (`thinking_budget=0`, `temperature=0.0`, Pydantic JSON-schema constrained decoding)  
**Methodology:** Optimal bipartite 1-to-1 task matching ($\tau = 0.32$ lexical Dice/$F_1$), 1,000-resample bootstrap 95% confidence intervals (`seed=42`), evaluated across 5 linguistic & adversarial strata.

---

## 1. End-to-End 3-Way Ablation Study (Core Results)

| Model Variant | Task Precision | Task Recall | Task Micro-$F_1$ (95% CI) | Owner Acc | Due-Date ($\pm 1$d) | NER Micro-$F_1$ (95% CI) | Topic Micro-$F_1$ | Latency p50 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. Rule & Gazetteer NLP Baseline** | 79.5% | 59.6% | **68.1%** `[54.8%, 79.5%]` | 71.0% | 93.5% | **76.9%** `[73.6%, 80.3%]` | 46.2% | **0.1 ms** |
| **2. Gemini Flash (Unconstrained)** | 94.5% | 100.0% | **97.2%** `[92.5%, 100.0%]` | 100.0% | 100.0% | **91.9%** `[89.6%, 94.0%]` | **67.4%** | 6,703 ms |
| **3. Gemini Flash + Guardrails (Prod)** | **100.0%** | **100.0%** | **100.0%** `[100.0%, 100.0%]` | **100.0%** | **100.0%** | **92.0%** `[89.7%, 94.1%]` | 65.6% | 5,905 ms |

---

## 2. Hallucination, Specificity & Adversarial Safety Metrics

| Model Variant | Verbatim Quote Grounded % | Zero-Task Specificity ($N=14$ Hard Negatives) | False-Positive Tasks on Negative Emails | Prompt-Injection Block Rate ($N=7$) |
| :--- | :---: | :---: | :---: | :---: |
| **1. Rule & Gazetteer NLP Baseline** | **100.0%** | 78.6% (`11/14`) | 5 FP tasks | **7/7** (ASR 0.0%) |
| **2. Gemini Flash (Unconstrained)** | **100.0%** | 85.7% (`12/14`) | 3 FP tasks | **7/7** (ASR 0.0%) |
| **3. Gemini Flash + Guardrails (Prod)** | **100.0%** | **100.0%** (`14/14`) | **0 FP tasks** | **7/7** (ASR 0.0%) |

---

## 3. Task Extraction $F_1$ Breakdown by Linguistic Stratum

| Linguistic Stratum | Emails ($N$) | Rule/Taxonomy Baseline $F_1$ | Gemini (Unconstrained) $F_1$ | Gemini + Guardrails (Prod) $F_1$ |
| :--- | :---: | :---: | :---: | :---: |
| **1. Explicit Numbered/Bulleted Threads** | 10 | 100.0% (`17/17` TP) | 100.0% | **100.0%** |
| **2. Implicit Conversational Prose (No Bullets)** | 14 | **38.1%** (`23.5%` Recall) | 100.0% | **100.0%** |
| **4. Multi-Turn Reassignments & Relative Dates** | 10 | **60.9%** (`53.8%` Recall) | 100.0% | **100.0%** |
| **5. Adversarial Prompt-Injection Threads** | 7 | 75.0% | 100.0% | **100.0%** |

*(Note: Stratum 3 `hard_negatives_zero_task` [$N=14$] contains 0 ground-truth tasks by design—covering past-tense completions, OOO auto-replies, newsletters, speculative brainstorming, and deferred customer wishlists—and is evaluated via Zero-Task Specificity & False-Positive count in Section 2.)*

---

## 4. Named Entity Recognition (NER) Granular Breakdown (In-Vocab vs. OOV Generalization)

| Entity Type | Rule/Gazetteer Baseline ($P / R / F_1$) | Gemini + Guardrails Prod ($P / R / F_1$) | Empirical Finding |
| :--- | :---: | :---: | :--- |
| **Person** | 96.2% / 95.5% / **95.8%** | 99.2% / 100.0% / **99.6%** | RFC-5322 header + directory lookup covers most people; Gemini resolves inline prose mentions. |
| **Organization (External)** | 32.7% / 31.5% / **32.1%** | 63.4% / 83.3% / **72.0%** | Gazetteer misses OOV vendors (`Snowflake`, `Deloitte`, `Stripe`, `Datadog`, `Carta`, `Okta`, `Vanta`); Gemini boosts Org Recall by **+51.8 pts** (`31.5%` $\to$ `83.3%`). |
| **Location** | 100.0% / 59.3% / **74.4%** | 93.1% / 100.0% / **96.4%** | Gazetteer misses OOV cities (`Frankfurt`, `Tokyo`, `Paris`, `Dublin`, `Singapore`, `Berlin`); Gemini boosts Location Recall by **+40.7 pts** (`59.3%` $\to$ `100.0%`). |

---

## 5. Concrete Empirical Error Analysis (From [`benchmark_results.json`](benchmark_results.json))

### A. Where the Rule & Gazetteer Baseline Fails (`68.1%` Task $F_1$, `71.0%` Owner Acc)
1. **Conversational Requests Without Bullets (`eval-015`, `eval-016`, `eval-020`)**: Because non-bulleted lines require rigid `Name: verb ... YYYY-MM-DD` triggers to avoid false positives, the heuristic engine missed `13/17` tasks in `implicit_conversational` (`23.5%` recall), such as *"I'll mark up the liability and auto-renewal language by 2026-11-07, and I need you to sign off on the committed host count in NetSuite by 2026-11-08"* (`eval-015`).
2. **Owner Attribution Swap on Dual-Speaker Prose (`eval-019`)**: When Jordan Taylor wrote to Priya Nair *"Can you send me three bullet points... by 2026-11-10? I'll stitch them... by 2026-11-12"*, the heuristic defaulted task ownership to the email sender (`Jordan Taylor`) rather than resolving second-person `"you"` to recipient `Priya Nair`, reducing owner attribution accuracy to **71.0%** (vs. **100.0%** with Gemini).
3. **Quoted History & Deferred Forward Leakage (`eval-033`, `eval-047`)**: Line-level regex scanning extracted superseded tasks inside `> On 2026-10-29...` reply quotes and inside forwarded deferred customer wishlists (`5` false positives on hard negatives).

### B. Where Unconstrained Gemini Fails vs. Guarded Production (`94.5%` $\to$ `100.0%` Precision)
1. **Deferred Forwarded Customer Wishlists (`eval-047`, 2 FPs)**: When Jordan forwarded Acme Corp's wishlist explicitly stating *"forwarding purely for future Q3 backlog context... do NOT work on or schedule these items now"*, `gemini_unconstrained` ignored the sender's framing and extracted both forwarded bullets (`Priya Nair: Custom SCIM group-sync connector` and `Marcus Vance: On-prem airgapped Helm installer`).
2. **Speculative Discussion Prompts (`eval-049`, 1 FP)**: When Sarah wrote *"Don't pull any reports or start an evaluation yet—let's just chat for 5 minutes live"*, `gemini_unconstrained` over-extracted `"5-minute live discussion regarding Stripe Billing vs. Chargebee"` as a scheduled deliverable.
3. **Residual Tradeoff (Organization Precision `63.4%` & Topic Micro-$F_1$ `65.6%`)**: Even in production mode, Gemini extracts fine-grained product/service names (`S3`, `Route53`, `VPC`, `Grafana`) as `Organization` entities alongside parent companies (`AWS`), and predicts adjacent multi-label taxonomy categories (e.g. tagging an IAM key rotation thread under `Cloud Infrastructure` in addition to `Cybersecurity & SOC2`).

---

## 6. Reproducing This Benchmark

```bash
# 1. Regenerate the N=55 stratified gold dataset
python3 -s eval/build_dataset.py

# 2. Run the 3-way ablation benchmark (Rule Baseline vs Unconstrained Gemini vs Guarded Production)
python3 -s -m eval.run_benchmark
```
