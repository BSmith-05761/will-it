# Willit Business Logic Phases (Detailed)

Purpose: Enumerate, in practical detail, everything we must determine to support a user in creating a complete, jurisdiction-aware will. This is a standalone reference for prompts, flows, and UI, independent from frameworks or typing systems. Prefer plain strings for states; introduce enums only when absolutely necessary.

## Global Principles
- Collect before drafting: aggressively surface missing info as gaps and resolve them conversationally.
- Ask fewer, better questions: propose the next 1–3 highest-value questions at a time.
- Jurisdiction-aware from the start: witness counts, notarization, community property, elective share, small-estate rules.e.g.("before we start, Where are you from? Where do you reside?") 
- Non‑probate audit: capture beneficiary designations and TOD/POD to avoid conflicts.
- Defaults with transparency: when applying a safe default, note the assumption and allow override.
- Conflict detection: highlight inconsistencies (e.g., specific gift of account that is TOD to someone else).
- Accessibility & privacy: simplify language, support multi-lingual hints later, minimize sensitive data.
- Always default to simple to understand explainations (Not only the legal jargon) 

## Phase 0 — Eligibility, Consent, and Capacity
Determine:
- Age of testator and jurisdictional age minimum.
- Mental capacity and absence of undue influence or duress (self‑attestation statement; we do not diagnose, we capture intent).
- Consent to data handling and storage; acceptance of non‑legal‑advice disclaimer.
- Whether the user intends this to be their Last Will and Testament and to revoke prior wills/codicils.

Outputs needed:
- `eligibility.ok`, `eligibility.notes`, `disclaimer_ack`, `intent_last_will`.
- Gaps if any: `eligibility_blocker`, `disclaimer_missing`.

## Phase 1 — Jurisdiction and Domicile
Determine:
- Country, state/province, county (or equivalent), and current domicile.
- Community‑property vs common‑law regime; elective‑share rights; state estate/inheritance tax regime.
- RUFADAA adoption for digital assets; self‑proving affidavit availability; witness count and qualifications; notary requirements; remote online notarization legality.
- Secondary jurisdictions: real property or other assets located in other states/countries (possible ancillary probate).

Outputs needed:
- `jurisdiction.primary`, `jurisdiction.secondary[]`, `rules.witness_count`, `rules.witness_disinterested`, `rules.self_proving_allowed`, `rules.notary_required`, `rules.120_hour_rule`, `rules.community_property`.
- Gaps: `jurisdiction_unknown`, `asset_situs_unknown`.

## Phase 2 — Identity and Contact
Determine:
- Full legal name, aliases/also‑known‑as, date of birth.
- Current residential address (domicile), mailing address if different.
- Preferred email and phone for follow‑up (optional).

Outputs needed:
- `testator.name`, `testator.aliases[]`, `testator.dob`, `testator.address`, `testator.contact`.
- Gaps: `name_missing`, `address_missing`.

## Phase 3 — Family and Relationships
Determine:
- Marital/relationship status: single, married, domestic partnership/civil union, separated, divorced, widowed.
- Spouse/partner identity; prenuptial/postnuptial agreements; community/separate property characterization.
- Prior marriages/partners; obligations (alimony, property agreements).
- Children and dependents: biological, adopted, stepchildren; minors/adults; special needs; unborn/pregnancy; children from prior relationships.
- Guardians for minor or dependent children: person vs estate; primary and alternates; co‑guardians option; compensation; temporary guardians.

Outputs needed:
- `relationships.status`, `spouse.name?`, `agreements.prenup?`, `children[]` with `{name, dob, parentage, special_needs?, dependent?}`.
- `guardians.person.primary/alternate[]`, `guardians.estate.primary/alternate[]`.
- Gaps: `guardian_missing`, `child_list_incomplete`, `prenup_unknown`.

## Phase 4 — Fiduciaries (Executors, Trustees, Agents)
Determine:
- Executor/Personal Representative: primary and alternates; corporate executor option; compensation; bond requirement waived or required; independent administration allowed.
- Trustees for any testamentary trusts; powers; removal and replacement mechanism; corporate trustee option.
- Digital assets agent under RUFADAA (may be executor or separate); scope of access.
- Funeral or disposition agent (who can direct remains and ceremony) if allowed by law.

Outputs needed:
- `executor.primary`, `executor.alternates[]`, `executor.compensation`, `executor.bond_waived`.
- `trustee.primary`, `trustee.alternates[]`, `trustee.removal_rules`.
- `agents.digital_assets`, `agents.funeral_directive?`.
- Gaps: `executor_missing`, `trustee_missing` (if trusts present).

## Phase 5 — Assets Inventory
Determine:
- Real property: addresses, ownership type (sole, joint tenants, tenants in common), community/separate characterization, mortgages, homestead/exemptions, any beneficiary deed/TOD deed.
- Bank/brokerage: account types, institutions, ownership, POD/TOD designations.
- Retirement and insurance: IRAs, 401(k), pensions, life insurance; current beneficiaries (non‑probate).
- Business interests: LLC/partnership/corporation shares; buy‑sell or transfer restrictions.
- Vehicles/boats/aircraft with titles.
- Tangible personal property: valuable items; whether to use a separate memorandum.
- Digital assets: crypto wallets/keys, exchanges, domains, social/email/cloud accounts; custody instructions (we capture intent and appoint access agent; we do not store secrets).
- Foreign assets and their situs considerations.
- Debts and liabilities overview.

Outputs needed:
- `assets.real_property[]`, `assets.financial[]`, `assets.retirement[]`, `assets.insurance[]`, `assets.business[]`, `assets.vehicles[]`, `assets.tangible[]`, `assets.digital[]` with minimal identification for mapping gifts.
- Gaps: `asset_unknown_ownership`, `beneficiary_designation_unknown`.

## Phase 6 — Non‑Probate Audit (Designations)
Determine:
- Current beneficiary designations for retirement, life insurance, annuities, POD/TOD accounts; survivorship on joint accounts.
- Conflicts with intended will plan; need for updates via provider forms.

Outputs needed:
- `designations[]` with `{asset_ref, primary[], contingent[]}` and a `conflict_flag` if misaligned.
- Gaps: `designation_missing`, `designation_conflict`.

## Phase 7 — Beneficiaries and Bequests
Determine:
- Specific gifts: items/sums to named beneficiaries; include item identification (uploads/photos help), location, and contingencies.
- Memorandum for tangible personal property: whether to enable and how to reference it.
- Charitable gifts: organizations, EINs if known, purpose restrictions, alternates.
- Residuary distribution: define shares and representation method (per stirpes, by representation/per capita) and hotchpot treatment.
- Survivorship requirement (e.g., 30–120 days) for beneficiaries to avoid double probate.
- Lapse/anti‑lapse handling and contingent beneficiaries.
- Pet care and related funds.

Outputs needed:
- `bequests.specific[]`, `bequests.charitable[]`, `bequests.memorandum_enabled`, `residuary.plan` with `{method, shares[], survivorship_days}`.
- `contingents[]` for alternates on specific gifts and residuary shares.
- Gaps: `residuary_undefined`, `gift_ambiguous_item`, `no_contingents`.

## Phase 8 — Trusts (Minors, Special Needs, Pets, Education)
Determine:
- Minors’ trusts: coverage (which beneficiaries), distribution ages or stages, HEMS standard, discretionary vs mandatory distributions, sprinkling vs separate shares, termination triggers, trustee powers.
- UTMA/UGMA alternative: state selection and age of termination when using custodianship instead of trust.
- Special Needs Trust (third‑party): for disabled beneficiaries; preserve means‑tested benefits; distribution constraints; trustee and successor; no payback for third‑party SNT.
- Spendthrift protection: restrict voluntary/involuntary transfer of beneficiary interests.
- Pet trust: caretaker, trustee, funding amount, remainder on pet’s death.
- Education trusts: permitted uses, duration, remainder.
- Trust protector or advisor roles: scope of powers, replacement rules.

Outputs needed:
- `trusts.minors`, `trusts.snt`, `trusts.pet`, `trusts.education`, including trustees and powers.
- Gaps: `trust_terms_missing`, `custodianship_state_missing`.

## Phase 9 — Taxes, Debts, and Apportionment
Determine:
- How estate/inheritance taxes are apportioned among beneficiaries (e.g., paid from residuary vs equitable apportionment).
- Marital deduction/QTIP directions if applicable; portability disclaimers (advanced, optional).
- Debt payment preferences and order of abatement when estate is insufficient.

Outputs needed:
- `taxes.apportionment`, `taxes.state_estate_tax?`, `marital_qtip_directive?`, `debts.payment_prefs`, `abatement.order`.
- Gaps: `apportionment_unspecified`.

## Phase 10 — Disinheritance and Family Protections
Determine:
- Intentional disinheritance (name the person, if desired, and state intent clearly).
- Omitted child/spouse protections: pretermitted child clause; after‑born/adopted children; elective share/community property implications.
- In terrorem (no‑contest) clause preference and jurisdictional enforceability.

Outputs needed:
- `disinheritance[]`, `pretermitted_children_clause`, `no_contest_clause`.
- Gaps: `disinherit_target_unclear`, `no_contest_policy_unsure`.

## Phase 11 — Administrative and Boilerplate Powers
Determine:
- Executor/trustee powers: sell/lease, invest, borrow, allocate receipts/disbursements between principal and income, compromise claims, employ professionals, retain assets.
- Digital assets authority under RUFADAA (explicitly grant access and disclosure rights).
- Custodian under UTMA/UGMA for small gifts to minors: state and age of termination.
- Governing law, venue, severability, gender‑neutral drafting, notice provisions.
- Simultaneous death/common disaster and survivorship rules (120‑hour or specified).
- Revocation of prior wills and codicils.

Outputs needed:
- `powers.executor`, `powers.trustee`, `powers.digital_assets`, `utma.state`, `utma.age`, `governing_law`, `revocation_clause`.
- Gaps: `powers_scope_unspecified`.

## Phase 12 — Execution and Witnessing Plan
Determine:
- Witnessing: number required, disinterested requirement, who qualifies, whether the chosen witnesses are beneficiaries (avoid).
- Notary and self‑proving affidavit availability and forms; remote online notarization rules.
- Signing session logistics: where, when, who attends; printing/initialing requirements; page numbering; attaching property memorandum.
- Storage plan for original and copies; whether to register with a will registry (if available).

Outputs needed:
- `execution.witness_count`, `execution.disinterested`, `execution.notary`, `execution.self_proving`, `execution.plan` (checklist steps), `storage.location`, `registration.plan?`.
- Gaps: `witness_plan_missing`, `notary_availability_unknown`.

## Phase 13 — Review, Drafting, and Export
Determine:
- Clause‑by‑clause confirmation; unresolved gaps to highlight; assumptions to confirm.
- Export preferences: DOCX/PDF; include self‑proving affidavit and UTMA form templates when applicable; include memorandum template.

Outputs needed:
- `review.flags[]`, `review.accepted_assumptions[]`, `export.formats[]`, `export.include_affidavit`, `export.include_memorandum_template`.
- Gaps: `unresolved_blockers`.

## Phase 14 — Post‑Execution Follow‑ups
Determine:
- Update beneficiary designations and TOD/POD registrations to match plan.
- Retitle assets as needed; update payable‑on‑death forms.
- Share will location and executor/trustee contacts; create/update a digital vault (without secrets).
- Reminder cadence to revisit plan after life events.

Outputs needed:
- `post_exec.tasks[]`, `post_exec.reminders[]`, `post_exec.vault_created?`.

## Cross‑Cutting: Gaps and Conflicts
- Every phase emits `gaps[]` with `{id, description, severity: BLOCKING|ADVISORY, suggested_question}`.
- Conflicts: designation vs will, community property vs separate characterization, beneficiary age vs distribution rule, witness disinterest, asset situs vs jurisdiction.
- The agent always proposes next questions prioritizing BLOCKING gaps.

## Cross‑Cutting: Uploads and Evidence
- Allow users to upload images/docs of assets, beneficiary info, prenups, prior wills.
- OCR + extraction to pre‑fill facts; link snippet to question for transparency.
- Support an item photo to identify a specific bequest target; prompt to add make/model/serial if needed.

## Cross‑Cutting: Safety and Disclaimers
- Not legal advice; user must ensure compliance and consult counsel if needed.
- We surface jurisdictional constraints but do not guarantee validity.
- We avoid storing secrets (keys/passwords); only capture intent and designate an access agent.

## Minimal Data Checklist (for completeness)
- Identity: name, DOB, address, aliases.
- Jurisdiction: domicile, community property, witness/notary rules.
- Relationships: spouse/partner, prior spouses, children (names, DOBs, special needs), guardians.
- Fiduciaries: executor (+ alternates), trustee(s), digital assets agent, funeral agent.
- Assets: property list (real, financial, retirement/insurance, business, vehicles, tangible, digital), ownership, situs.
- Designations: current beneficiaries for non‑probate assets (primary/contingent) and conflicts.
- Bequests: specific gifts, charitable gifts, pets, residuary plan, contingents, survivorship.
- Trusts: minors’ trust terms or UTMA, SNT if needed, spendthrift, pet/education trusts, trustees.
- Taxes/debts: apportionment, abatement, marital/QTIP directives (optional).
- Admin/boilerplate: powers, digital authority, UTMA, governing law, revocation, simultaneous death.
- Execution: witnesses, notary, self‑proving, logistics, storage/registration.
- Post‑execution: designation updates, retitling, vault, reminders.

This document guides prompts, flows, and validations. Use it to define gaps, next questions, and drafting logic.
