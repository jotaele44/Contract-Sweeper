# Interpreting the documents you'll be handed

Ingestion is not summarization. Each document type answers a different question.
This file is the lookup table.

---

## Audit reports (Contralor / OIG / GAO / IG)

**What it is:** what the auditor could *prove*, within scope, within the period.

**Read it for:**
- **What they COULDN'T get.** "The agency did not provide X" is not a footnote — it's often the loudest fact in the report. If the missing document would have disqualified someone, its absence is evidence.
- **Anonymized contractors** ("Contractor A", "Company X"). **The contract numbers are usually still printed.** Those numbers are the public join-key. Look them up in the contract registry and the anonymity collapses.
- **The opinion type.** *Adverse* means the operations examined did not comply with law. That is the strongest thing an auditor says.
- **Annexes.** The tables and photos at the back carry the specifics the narrative smooths over.

**Do NOT treat the findings as the ceiling.** They're the floor.

---

## Contract registries

**What it is:** the spine of the whole investigation.

**Get, for every contract:** exact legal name, contract number, amount, date of grant, effective dates, service classification, amendment flag, cancellation date.

**Read it for:**
- **Service misclassification.** A real-estate firm filed under "administrative consulting." An LNG advisory firm filed under "legal." The label is chosen by the agency and is sometimes camouflage.
- **Amendment flags.** Abuse lives in amendments — money added after the fact, sometimes after expiry.
- **The date of grant vs. the emergency.** If the contract predates the emergency that justified skipping the bid, the emergency was not the reason.
- **Term length.** Compare the construction contract term to the *oversight* contract term. (See the oversight-vacuum check.)

---

## Corporate registries and annual reports

**What it is:** the capacity test's raw material.

**Get:** registration date, status, officers (all roles), registered address, and — critically — **who holds which office**.

**Read it for:**
- One person holding President + Treasurer + Agent + sole shareholder = no institutional capacity.
- A registered office that is a residence.
- **Name variants.** Spanish/English spelling differences ("ADQuisitions" vs "ACQuisitions") will make a real company look nonexistent. **Test variants before concluding anything.**
- Structural limits: many registries have **no officer-name search**. You cannot ask "what else does this person control." Say so; don't fake it.

---

## Audited financial statements

**What it is:** where the case is won or lost.

Usually **scanned** — `pdfplumber` returns nothing. Render (`pdftoppm -r 300 -png`) and OCR (`tesseract`).

**Get:**
- **Revenue, by year.** Especially the year *before* the first award.
- **Total equity** at the balance-sheet date nearest the award.
- **"Cost of Services" ÷ Revenue** ← the pass-through ratio. This single number is the strongest diagnostic in the method.
- **Notes on related parties.** Auditors name "affiliates" even when the registry doesn't.
- Fixed assets. Compare what they own to what the work requires.

---

## Strategic plans, press releases, official announcements

**What it is:** the institution describing itself.

**Read it for the gap between promise and practice.**
- **Announced cost ≠ contracted cost.** Check both. A 33% gap between the announced figure and the actual contract is the kind of thing nobody reports.
- Governance language ("our board is independent of political influence") is often written *in response to* a prior scandal. Note what it's defending against.
- Named programs — cash-advance mechanisms, expedited processes — are procurement instruments. Find out who administers them.

**Never cite an announcement as if it were a contract.**

---

## Engineering deliverables, technical papers, design reports

**What it is:** proof that work happened, and by whom.

**Read it for:**
- **Author affiliation.** The firm that actually did the engineering is on the cover. If that isn't the prime contractor, you've found the pass-through without needing the financials.
- Scale and scope — does the technical reality match the contracted scope?
- Dates — was the design done before or after the contract that supposedly paid for it?

---

## Court filings

Chronically underused, entirely public, and devastating.

- **Wage suits** by employees establish insolvency — often at the exact moment the agency was calling the firm financially sound.
- **Foreclosures** establish the same.
- **Injunctions** establish what the project's opponents knew and when.
- Expropriation cases name the appraisers and agents — i.e. the subcontractors on the land-acquisition side.

If an agency claimed a contractor had "solvencia económica" while that contractor was being sued by its own staff for unpaid wages, **the public docket is your evidence.**
