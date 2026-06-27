"""Generate an expanded labeled eval corpus for Layer 3 fine-tuning bake-off.

Reads the existing benchmark JSONL seeds (99 examples) and produces an
expanded corpus of 600+ labeled examples (200 per domain) via deterministic
template-substitution — no LLM, no network, no GPU required.

Output files (in ``benchmarks/eval_corpus/``):
  - ``legal_privilege_expanded.jsonl``
  - ``therapy_phi_expanded.jsonl``
  - ``finance_mnpi_expanded.jsonl``

These are kept separate from the production benchmark fixtures (benchmarks/*.jsonl)
so the OGE-320 harness (run_benchmarks.py) is unaffected.

JSONL schema (same as production fixtures):
    {
      "id": "legal-gen-001",
      "text": "...",
      "expected_entities": [{"type": "PRIVILEGE_MARKER"}, ...],
      "expected_level": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "NONE",
      "category": "true_positive" | "true_negative" | "adversarial_negative",
      "notes": "..."
    }

Usage:
    python benchmarks/generate_eval_corpus.py
    python benchmarks/generate_eval_corpus.py --output-dir /tmp/corpus
    python benchmarks/generate_eval_corpus.py --per-domain 300 --seed 42
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BENCHMARKS_DIR = Path(__file__).parent
DEFAULT_OUTPUT_DIR = BENCHMARKS_DIR / "eval_corpus"
DEFAULT_PER_DOMAIN = 200
DEFAULT_SEED = 0


# ── Entity substitution tables ────────────────────────────────────────────────

LAW_FIRMS = [
    "Davis Polk & Wardwell",
    "Wachtell Lipton Rosen & Katz",
    "Cravath Swaine & Moore",
    "Sullivan & Cromwell",
    "Skadden Arps Slate Meagher & Flom",
    "Latham & Watkins",
    "Gibson Dunn & Crutcher",
    "Simpson Thacher & Bartlett",
    "Paul Weiss Rifkind Wharton & Garrison",
    "Kirkland & Ellis",
    "Cleary Gottlieb Steen & Hamilton",
    "Debevoise & Plimpton",
    "Covington & Burling",
    "WilmerHale",
    "Morrison & Foerster",
]

CASE_PREFIXES = [
    "1:24-cv", "2:24-cv", "3:25-cv", "4:25-cv", "1:25-cv",
    "2:25-cv", "3:24-cv", "1:26-cv", "2:26-cv",
]

CASE_SUFFIXES = [
    "00123", "00456", "01234", "07891", "00987",
    "00321", "01111", "02222", "03333", "04444",
]

BATES_PREFIXES = [
    "MERIDIAN", "ALPHA", "TITAN", "NEXUS", "VERTEX",
    "CREST", "SUMMIT", "APEX", "PRISM", "VANTAGE",
]

SETTLEMENT_AMOUNTS = [
    "$850,000", "$1.2M", "$4.2M", "$7.5M", "$15M",
    "$250,000", "$500,000", "$3.8M", "$2.1M", "$9.5M",
    "$425,000", "$1.75M", "$6.3M", "$12M", "$22.5M",
]

EXECUTIVE_TITLES = [
    "CEO", "CFO", "General Counsel", "CLO", "COO",
    "Chief Risk Officer", "Chief Compliance Officer",
    "Managing Director", "Executive Vice President",
]

LEGAL_MATTERS = [
    "the Johnson matter", "the SEC investigation",
    "the antitrust review", "the regulatory inquiry",
    "the breach of contract dispute", "the employment matter",
    "the class action", "the patent dispute",
    "the IP litigation", "the securities fraud case",
]

PATIENT_NAMES = [
    "John Smith", "Maria Garcia", "James Johnson", "Emily Chen",
    "Robert Williams", "Sarah Davis", "Michael Brown", "Lisa Martinez",
    "David Wilson", "Jennifer Taylor", "Christopher Anderson", "Amanda Thomas",
    "Daniel Jackson", "Rebecca Harris", "Matthew Thompson",
]

DOBS = [
    "03/15/1985", "07/22/1972", "11/04/1990", "01/30/1968",
    "09/18/1955", "06/12/1999", "02/28/1980", "12/05/1963",
    "04/17/1978", "08/09/1945", "05/25/1992", "10/31/1987",
]

DIAGNOSIS_CODES = [
    ("F32.9", "major depressive disorder"),
    ("F41.1", "generalized anxiety disorder"),
    ("F33.0", "recurrent depressive disorder"),
    ("F31.9", "bipolar disorder unspecified"),
    ("F43.1", "post-traumatic stress disorder"),
    ("F40.10", "social anxiety disorder"),
    ("F60.3", "borderline personality disorder"),
    ("F20.9", "schizophrenia unspecified"),
    ("F50.00", "anorexia nervosa"),
    ("F90.0", "ADHD predominantly inattentive"),
]

MEDICATIONS = [
    "sertraline 100mg", "fluoxetine 20mg", "escitalopram 10mg",
    "bupropion 150mg", "venlafaxine 75mg", "lithium 600mg",
    "quetiapine 25mg", "aripiprazole 5mg", "lamotrigine 100mg",
    "lorazepam 1mg PRN", "clonazepam 0.5mg", "alprazolam 0.25mg",
    "risperidone 2mg", "olanzapine 5mg", "duloxetine 60mg",
]

INSURANCE_IDS = [
    "XYZ987654321", "ABC123456789", "MNO555666777",
    "PQR444555666", "DEF789012345", "GHI321654987",
    "JKL111222333", "STU888999000", "VWX777888999",
]

INSURANCE_COMPANIES = [
    "Cigna PPO", "Aetna HMO", "Blue Cross Blue Shield",
    "UnitedHealthcare", "Humana", "Anthem PPO",
    "Magellan Health", "Optum Behavioral Health",
]

FINANCE_INSTITUTIONS = [
    "Goldman Sachs", "JPMorgan", "Morgan Stanley",
    "Citigroup", "Bank of America", "Barclays",
    "Credit Suisse", "Deutsche Bank", "UBS",
    "Blackstone", "KKR", "Apollo Global Management",
    "Carlyle Group", "Warburg Pincus", "Vista Equity Partners",
]

TARGET_COMPANIES = [
    "TechCorp", "Alpha Corp", "Beta Industries", "Meridian Holdings",
    "Apex Systems", "Vertex Technologies", "Nexus Media",
    "Titan Financial", "Crest Capital", "Summit Partners",
    "Prism Analytics", "Vantage Health", "Clarity Networks",
    "Horizon Pharma", "Catalyst Group",
]

DEAL_VALUES = [
    "$850M", "$1.5B", "$2.5B", "$4.2B", "$750M",
    "$3.8B", "$6.5B", "$12B", "$500M", "$1.1B",
    "$7.2B", "$300M", "$450M", "$2.1B", "$8.5B",
]

LEVERAGE_RATIOS = [
    "5.5x EBITDA", "6.5x EBITDA", "4.0x EBITDA",
    "7.0x leverage", "5.0x net debt", "6.0x senior leverage",
    "4.5x total leverage",
]

FUND_NAMES = [
    "Fund III", "Fund IV", "Fund V",
    "Opportunity Fund II", "Growth Fund III",
    "Credit Fund IV", "Real Assets Fund II",
]

CARRY_TERMS_LIST = [
    "20% over an 8% hurdle",
    "20% carried interest over 7% preferred return",
    "15% carry above a 9% IRR hurdle",
    "20% carry, 8% preferred, European waterfall",
    "25% incentive fee above high-water mark",
]

PROVIDERS = [
    "Dr. Sarah Kim", "Dr. James Park", "Dr. Maria Santos",
    "Dr. Robert Chen", "Dr. Lisa Nguyen", "Dr. Michael Davis",
    "Dr. Angela Wright", "Dr. Carlos Rivera",
]


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class Example:
    id: str
    text: str
    expected_entities: list[dict[str, str]]
    expected_level: str
    category: str
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "expected_entities": self.expected_entities,
            "expected_level": self.expected_level,
            "category": self.category,
            "notes": self.notes,
        }


# ── Generator ─────────────────────────────────────────────────────────────────

class CorpusGenerator:
    def __init__(self, seed: int = DEFAULT_SEED):
        self._rng = random.Random(seed)

    def _pick(self, seq: list) -> Any:
        return self._rng.choice(seq)

    def _picks(self, seq: list, k: int) -> list:
        return self._rng.sample(seq, k)

    # ── Legal: true positives ──────────────────────────────────────────────

    def _legal_tp(self, idx: int) -> Example:
        template_idx = idx % 10
        if template_idx == 0:
            firm = self._pick(LAW_FIRMS)
            matter = self._pick(LEGAL_MATTERS)
            return Example(
                id=f"legal-gen-tp-{idx:03d}",
                text=f"Privileged & confidential — attorney-client communication. {firm} advises on {matter}.",
                expected_entities=[
                    {"type": "PRIVILEGE_MARKER"}, {"type": "ATTORNEY_CLIENT"},
                    {"type": "COUNSEL_COMMUNICATION"}, {"type": "LAW_FIRM_NAME"},
                ],
                expected_level="CRITICAL",
                category="true_positive",
                notes=f"Privilege marker + firm + matter — gen {idx}",
            )
        elif template_idx == 1:
            matter = self._pick(LEGAL_MATTERS)
            return Example(
                id=f"legal-gen-tp-{idx:03d}",
                text=f"This memorandum constitutes attorney work product prepared in anticipation of litigation regarding {matter}.",
                expected_entities=[{"type": "WORK_PRODUCT"}, {"type": "LITIGATION_MARKER"}],
                expected_level="HIGH",
                category="true_positive",
                notes=f"Work product doctrine — gen {idx}",
            )
        elif template_idx == 2:
            amount = self._pick(SETTLEMENT_AMOUNTS)
            prefix = self._pick(CASE_PREFIXES)
            suffix = self._pick(CASE_SUFFIXES)
            return Example(
                id=f"legal-gen-tp-{idx:03d}",
                text=f"Confidential settlement of {amount} in Case No. {prefix}-{suffix} is privileged and non-disclosable.",
                expected_entities=[
                    {"type": "SETTLEMENT_TERMS"}, {"type": "CASE_NUMBER"}, {"type": "PRIVILEGE_MARKER"},
                ],
                expected_level="CRITICAL",
                category="true_positive",
                notes=f"Settlement + case number + privilege — gen {idx}",
            )
        elif template_idx == 3:
            bates_prefix = self._pick(BATES_PREFIXES)
            bates_num = self._rng.randint(100000, 999999)
            prefix = self._pick(CASE_PREFIXES)
            suffix = self._pick(CASE_SUFFIXES)
            return Example(
                id=f"legal-gen-tp-{idx:03d}",
                text=f"Bates-stamped document {bates_prefix}-{bates_num:06d} produced in discovery in litigation No. {prefix}-{suffix}.",
                expected_entities=[{"type": "BATES_NUMBER"}, {"type": "CASE_NUMBER"}],
                expected_level="HIGH",
                category="true_positive",
                notes=f"Bates + case number — gen {idx}",
            )
        elif template_idx == 4:
            firm = self._pick(LAW_FIRMS)
            matter = self._pick(LEGAL_MATTERS)
            return Example(
                id=f"legal-gen-tp-{idx:03d}",
                text=f"We retained {firm} to advise on {matter}; their legal advice is privileged.",
                expected_entities=[{"type": "LAW_FIRM_NAME"}, {"type": "PRIVILEGE_MARKER"}],
                expected_level="HIGH",
                category="true_positive",
                notes=f"Law firm retention + privilege — gen {idx}",
            )
        elif template_idx == 5:
            matter = self._pick(LEGAL_MATTERS)
            return Example(
                id=f"legal-gen-tp-{idx:03d}",
                text=f"Subject to the litigation hold, please preserve all electronic records related to {matter}.",
                expected_entities=[{"type": "LITIGATION_MARKER"}],
                expected_level="HIGH",
                category="true_positive",
                notes=f"Litigation hold — gen {idx}",
            )
        elif template_idx == 6:
            filings = ["motion to dismiss", "motion for summary judgment", "complaint", "answer and counterclaim"]
            f1, f2 = self._picks(filings, 2)
            return Example(
                id=f"legal-gen-tp-{idx:03d}",
                text=f"The {f1} was filed yesterday; we expect the {f2} to follow next week.",
                expected_entities=[{"type": "COURT_FILING"}, {"type": "COURT_FILING"}],
                expected_level="HIGH",
                category="true_positive",
                notes=f"Multiple court filings — gen {idx}",
            )
        elif template_idx == 7:
            t1, t2 = self._picks(EXECUTIVE_TITLES, 2)
            return Example(
                id=f"legal-gen-tp-{idx:03d}",
                text=f"This communication is privileged. The {t1} and {t2} must review before any external disclosure.",
                expected_entities=[
                    {"type": "PRIVILEGE_MARKER"}, {"type": "EXECUTIVE_NAME"}, {"type": "EXECUTIVE_NAME"},
                ],
                expected_level="HIGH",
                category="true_positive",
                notes=f"Privilege + executive titles — gen {idx}",
            )
        elif template_idx == 8:
            firm = self._pick(LAW_FIRMS)
            return Example(
                id=f"legal-gen-tp-{idx:03d}",
                text=f"{firm} advised that the deposition transcript should be marked attorneys' eyes only.",
                expected_entities=[{"type": "LAW_FIRM_NAME"}, {"type": "ATTORNEY_CLIENT"}],
                expected_level="HIGH",
                category="true_positive",
                notes=f"Law firm + AEO designation — gen {idx}",
            )
        else:
            districts = [
                "the Southern District of New York", "the Northern District of California",
                "the District of Delaware", "the Eastern District of Virginia",
            ]
            district = self._pick(districts)
            month = self._pick(["January", "March", "May", "August", "October", "December"])
            day = self._rng.randint(1, 28)
            year = self._rng.choice([2025, 2026])
            return Example(
                id=f"legal-gen-tp-{idx:03d}",
                text=f"The deposition was taken on {month} {day}, {year}, in the matter pending in {district}.",
                expected_entities=[{"type": "COURT_FILING"}],
                expected_level="HIGH",
                category="true_positive",
                notes=f"Deposition + court reference — gen {idx}",
            )

    def _legal_tn(self, idx: int) -> Example:
        t = idx % 4
        if t == 0:
            topic = self._pick(["breach of fiduciary duty", "negligence", "fraud", "defamation"])
            jx = self._pick(["Delaware", "New York", "California", "Texas", "federal"])
            return Example(
                id=f"legal-gen-tn-{idx:03d}",
                text=f"What are the elements of a {topic} claim under {jx} law?",
                expected_entities=[], expected_level="NONE", category="true_negative",
                notes="Generic legal question — no privileged content",
            )
        elif t == 1:
            subj = self._pick(["civil procedure", "contract law", "tort law", "administrative law"])
            return Example(
                id=f"legal-gen-tn-{idx:03d}",
                text=f"I'm researching {subj} rules for my law school class.",
                expected_entities=[], expected_level="NONE", category="true_negative",
                notes="Educational query — not privileged",
            )
        elif t == 2:
            case = self._pick(["Marbury v. Madison", "Brown v. Board of Education", "Miranda v. Arizona"])
            return Example(
                id=f"legal-gen-tn-{idx:03d}",
                text=f"Can you summarize the holding in {case}?",
                expected_entities=[], expected_level="NONE", category="true_negative",
                notes="Public case law reference",
            )
        else:
            topic = self._pick(["weather", "sports results", "restaurant review", "travel itinerary"])
            quality = self._pick(["great", "terrible", "unpredictable", "excellent"])
            return Example(
                id=f"legal-gen-tn-{idx:03d}",
                text=f"The {topic} is {quality} today.",
                expected_entities=[], expected_level="NONE", category="true_negative",
                notes="Off-topic — should never trigger",
            )

    def _legal_adv(self, idx: int) -> Example:
        t = idx % 4
        if t == 0:
            val = self._pick(["flexibility", "speed", "quality", "innovation"])
            rigid = self._pick(["schedules", "processes", "hierarchies", "rules"])
            return Example(
                id=f"legal-gen-adv-{idx:03d}",
                text=f"We should privilege {val} over rigid {rigid}.",
                expected_entities=[], expected_level="NONE", category="adversarial_negative",
                notes="'privilege' as a verb in non-legal context",
            )
        elif t == 1:
            item = self._pick(["accounts", "invoices", "monthly expenses", "vendor payments"])
            period = self._pick(["quarter", "month", "fiscal year"])
            return Example(
                id=f"legal-gen-adv-{idx:03d}",
                text=f"The settlement of {item} at the end of the {period} requires careful reconciliation.",
                expected_entities=[], expected_level="NONE", category="adversarial_negative",
                notes="'settlement' in accounting context",
            )
        elif t == 2:
            domain = self._pick(["marketing", "HR", "IT", "design", "financial"])
            return Example(
                id=f"legal-gen-adv-{idx:03d}",
                text=f"We need outside expertise. Counsel from a {domain} consultancy would be valuable.",
                expected_entities=[], expected_level="LOW", category="adversarial_negative",
                notes="'outside' + 'counsel' in non-legal context",
            )
        else:
            item = self._pick(["product launch", "hiring plan", "budget", "roadmap"])
            return Example(
                id=f"legal-gen-adv-{idx:03d}",
                text=f"Confidential — for internal review only. The new {item} is on schedule.",
                expected_entities=[], expected_level="LOW", category="adversarial_negative",
                notes="'confidential' alone — no legal markers",
            )

    # ── Therapy: true positives ────────────────────────────────────────────

    def _therapy_tp(self, idx: int) -> Example:
        t = idx % 10
        if t == 0:
            name = self._pick(PATIENT_NAMES)
            dob = self._pick(DOBS)
            code, dx = self._pick(DIAGNOSIS_CODES)
            med = self._pick(MEDICATIONS)
            return Example(
                id=f"therapy-gen-tp-{idx:03d}",
                text=f"Patient {name} (DOB {dob}) presents with {dx}, {code}, currently on {med}.",
                expected_entities=[
                    {"type": "PERSON"}, {"type": "DATE_OF_BIRTH"},
                    {"type": "DIAGNOSIS_CODE"}, {"type": "MEDICATION"},
                ],
                expected_level="CRITICAL", category="true_positive",
                notes=f"Full PHI cluster — name+DOB+dx+meds — gen {idx}",
            )
        elif t == 1:
            session_num = self._rng.randint(1, 50)
            therapy_type = self._pick([
                "cognitive behavioral therapy", "dialectical behavior therapy",
                "exposure and response prevention", "EMDR",
                "acceptance and commitment therapy",
            ])
            code, dx = self._pick(DIAGNOSIS_CODES)
            return Example(
                id=f"therapy-gen-tp-{idx:03d}",
                text=f"Session {session_num} with patient: continued {therapy_type} for {dx}, {code}.",
                expected_entities=[{"type": "SESSION_MARKER"}, {"type": "DIAGNOSIS_CODE"}],
                expected_level="HIGH", category="true_positive",
                notes=f"Session marker + ICD-10 — gen {idx}",
            )
        elif t == 2:
            risk = self._pick([
                "suicidal ideation with plan but denies current intent",
                "active suicidal ideation with a specific plan",
                "self-harm behaviour in the past 48 hours",
                "homicidal ideation toward a named individual",
            ])
            follow = self._pick([
                "Safety plan in place.", "Emergency referral initiated.",
                "Crisis team contacted.", "Inpatient evaluation arranged.",
            ])
            return Example(
                id=f"therapy-gen-tp-{idx:03d}",
                text=f"Patient endorses {risk}. {follow}",
                expected_entities=[{"type": "CLINICAL_RISK_FLAG"}],
                expected_level="CRITICAL", category="true_positive",
                notes=f"Clinical risk flag — gen {idx}",
            )
        elif t == 3:
            ins_id = self._pick(INSURANCE_IDS)
            insurer = self._pick(INSURANCE_COMPANIES)
            code, dx = self._pick(DIAGNOSIS_CODES)
            return Example(
                id=f"therapy-gen-tp-{idx:03d}",
                text=f"Insurance ID: {ins_id} — {insurer}. Diagnosis: {code} {dx}.",
                expected_entities=[{"type": "INSURANCE_ID"}, {"type": "DIAGNOSIS_CODE"}],
                expected_level="HIGH", category="true_positive",
                notes=f"Insurance + diagnosis code — gen {idx}",
            )
        elif t == 4:
            meds = self._picks(MEDICATIONS, 3)
            return Example(
                id=f"therapy-gen-tp-{idx:03d}",
                text=f"Patient is currently taking {meds[0]}, {meds[1]}, and {meds[2]}.",
                expected_entities=[
                    {"type": "MEDICATION"}, {"type": "MEDICATION"}, {"type": "MEDICATION"},
                ],
                expected_level="HIGH", category="true_positive",
                notes=f"Multiple psychiatric medications — gen {idx}",
            )
        elif t == 5:
            name = self._pick(PATIENT_NAMES)
            provider = self._pick(PROVIDERS)
            return Example(
                id=f"therapy-gen-tp-{idx:03d}",
                text=f"Progress note by {provider}: patient {name} shows improvement in affect regulation since last session.",
                expected_entities=[
                    {"type": "PROVIDER_NAME"}, {"type": "PATIENT_NAME"}, {"type": "SESSION_MARKER"},
                ],
                expected_level="HIGH", category="true_positive",
                notes=f"Provider + patient name + session — gen {idx}",
            )
        elif t == 6:
            topic = self._pick([
                "Substance use history discussed.", "Trauma processing session.",
                "Grief work continues.", "Family systems explored.",
            ])
            return Example(
                id=f"therapy-gen-tp-{idx:03d}",
                text=f"Psychotherapy note — do not include in general medical record per 42 CFR Part 2. {topic}",
                expected_entities=[{"type": "PSYCHOTHERAPY_NOTE_MARKER"}],
                expected_level="CRITICAL", category="true_positive",
                notes=f"Psychotherapy note marker — gen {idx}",
            )
        elif t == 7:
            name = self._pick(PATIENT_NAMES)
            dob = self._pick(DOBS)
            ssn = f"{self._rng.randint(100,999)}-{self._rng.randint(10,99)}-{self._rng.randint(1000,9999)}"
            return Example(
                id=f"therapy-gen-tp-{idx:03d}",
                text=f"Patient: {name}, DOB: {dob}, SSN: {ssn}. Intake assessment completed.",
                expected_entities=[
                    {"type": "PATIENT_NAME"}, {"type": "DATE_OF_BIRTH"}, {"type": "SSN"},
                ],
                expected_level="CRITICAL", category="true_positive",
                notes=f"Patient name + DOB + SSN — gen {idx}",
            )
        elif t == 8:
            code, dx = self._pick(DIAGNOSIS_CODES)
            return Example(
                id=f"therapy-gen-tp-{idx:03d}",
                text=f"Crisis intervention note: patient in acute distress, diagnosis {code}, admitted for observation.",
                expected_entities=[{"type": "CLINICAL_RISK_FLAG"}, {"type": "DIAGNOSIS_CODE"}],
                expected_level="CRITICAL", category="true_positive",
                notes=f"Crisis note + diagnosis — gen {idx}",
            )
        else:
            name = self._pick(PATIENT_NAMES)
            return Example(
                id=f"therapy-gen-tp-{idx:03d}",
                text=f"Safety plan reviewed with {name}. Patient denies current intent but reports passive ideation. Follow-up in 48 hours.",
                expected_entities=[{"type": "PATIENT_NAME"}, {"type": "CLINICAL_RISK_FLAG"}],
                expected_level="CRITICAL", category="true_positive",
                notes=f"Safety plan + patient name + risk flag — gen {idx}",
            )

    def _therapy_tn(self, idx: int) -> Example:
        t = idx % 4
        if t == 0:
            tech = self._pick(["mindfulness", "stress reduction", "relaxation", "breathing"])
            cond = self._pick(["work stress", "exam anxiety", "sleep issues", "general worry"])
            return Example(
                id=f"therapy-gen-tn-{idx:03d}",
                text=f"What are the best {tech} techniques for managing {cond}?",
                expected_entities=[], expected_level="NONE", category="true_negative",
                notes="Generic wellness question — not PHI",
            )
        elif t == 1:
            pair = self._pick(["CBT and DBT", "therapy and coaching", "anxiety and depression"])
            return Example(
                id=f"therapy-gen-tn-{idx:03d}",
                text=f"Can you explain the difference between {pair}?",
                expected_entities=[], expected_level="NONE", category="true_negative",
                notes="Educational mental health question",
            )
        elif t == 2:
            scope = self._pick(["team", "department", "company", "quarterly"])
            day = self._pick(["Tuesday", "Wednesday", "Thursday", "Friday"])
            return Example(
                id=f"therapy-gen-tn-{idx:03d}",
                text=f"I'd like to schedule a {scope} meeting for next {day}.",
                expected_entities=[], expected_level="NONE", category="true_negative",
                notes="Off-topic administrative message",
            )
        else:
            person = self._pick(["new employee", "team member", "candidate"])
            role = self._pick(["role", "team", "position", "department"])
            return Example(
                id=f"therapy-gen-tn-{idx:03d}",
                text=f"The {person} seems like a good fit for the {role}.",
                expected_entities=[], expected_level="NONE", category="true_negative",
                notes="HR context — no PHI",
            )

    def _therapy_adv(self, idx: int) -> Example:
        t = idx % 4
        if t == 0:
            qual = self._pick(["great", "remarkable", "impressive"])
            attr = self._pick(["patience", "resilience", "discipline"])
            period = self._pick(["market downturn", "volatile quarter", "correction"])
            return Example(
                id=f"therapy-gen-adv-{idx:03d}",
                text=f"The patient investor showed {qual} {attr} during the {period}.",
                expected_entities=[], expected_level="NONE", category="adversarial_negative",
                notes="'patient' as adjective in finance context",
            )
        elif t == 1:
            body = self._pick(["board", "committee", "council", "working group"])
            topic = self._pick(["budget planning", "risk management", "strategic initiatives"])
            return Example(
                id=f"therapy-gen-adv-{idx:03d}",
                text=f"Today's session of the {body} focused on {topic}.",
                expected_entities=[], expected_level="NONE", category="adversarial_negative",
                notes="'session' in business/governance context",
            )
        elif t == 2:
            item = self._pick(["marketing strategy", "product roadmap", "technical debt"])
            return Example(
                id=f"therapy-gen-adv-{idx:03d}",
                text=f"The diagnosis is clear: our {item} needs an overhaul.",
                expected_entities=[], expected_level="NONE", category="adversarial_negative",
                notes="'diagnosis' in business context — not clinical",
            )
        else:
            audience = self._pick(["team", "all staff", "the group"])
            doc = self._pick(["policy update", "training materials", "compliance guide"])
            return Example(
                id=f"therapy-gen-adv-{idx:03d}",
                text=f"Note to {audience}: please review the attached {doc} by Friday.",
                expected_entities=[], expected_level="NONE", category="adversarial_negative",
                notes="'note' in administrative context",
            )

    # ── Finance: true positives ────────────────────────────────────────────

    def _finance_tp(self, idx: int) -> Example:
        t = idx % 10
        if t == 0:
            target = self._pick(TARGET_COMPANIES)
            value = self._pick(DEAL_VALUES)
            return Example(
                id=f"finance-gen-tp-{idx:03d}",
                text=f"MNPI: pending acquisition of {target} valued at {value}; insider trading restrictions apply.",
                expected_entities=[
                    {"type": "MNPI_MARKER"}, {"type": "MA_ACTIVITY"},
                    {"type": "DEAL_VALUE"}, {"type": "INSIDER_MARKER"},
                ],
                expected_level="CRITICAL", category="true_positive",
                notes=f"MNPI + deal + insider — gen {idx}",
            )
        elif t == 1:
            t1, t2 = self._picks(TARGET_COMPANIES, 2)
            return Example(
                id=f"finance-gen-tp-{idx:03d}",
                text=f"Confidential — material non-public information regarding the proposed merger of {t1} with {t2}.",
                expected_entities=[{"type": "MNPI_MARKER"}, {"type": "MA_ACTIVITY"}],
                expected_level="CRITICAL", category="true_positive",
                notes=f"MNPI + M&A — gen {idx}",
            )
        elif t == 2:
            inst = self._pick(FINANCE_INSTITUTIONS)
            value = self._pick(DEAL_VALUES)
            carry = self._pick(CARRY_TERMS_LIST)
            return Example(
                id=f"finance-gen-tp-{idx:03d}",
                text=f"{inst} is advising on the {value} transaction; carry terms are {carry}.",
                expected_entities=[
                    {"type": "INSTITUTION_NAME"}, {"type": "DEAL_VALUE"}, {"type": "CARRY_TERMS"},
                ],
                expected_level="HIGH", category="true_positive",
                notes=f"Institution + deal + carry — gen {idx}",
            )
        elif t == 3:
            fund = self._pick(FUND_NAMES)
            value = self._pick(DEAL_VALUES)
            carry = self._pick(CARRY_TERMS_LIST)
            mgmt_fee = self._rng.choice(["1.5%", "1.75%", "2.0%", "1.0%"])
            return Example(
                id=f"finance-gen-tp-{idx:03d}",
                text=f"{fund} closed at {value} with a {mgmt_fee} management fee and {carry}.",
                expected_entities=[
                    {"type": "FUND_INFORMATION"}, {"type": "DEAL_VALUE"}, {"type": "CARRY_TERMS"},
                ],
                expected_level="HIGH", category="true_positive",
                notes=f"Fund close + carry — gen {idx}",
            )
        elif t == 4:
            target = self._pick(TARGET_COMPANIES)
            return Example(
                id=f"finance-gen-tp-{idx:03d}",
                text=f"Pre-announcement: do not trade {target} shares until the SEC filing is public.",
                expected_entities=[{"type": "INSIDER_MARKER"}],
                expected_level="CRITICAL", category="true_positive",
                notes=f"Pre-announcement insider warning — gen {idx}",
            )
        elif t == 5:
            ratio = self._pick(LEVERAGE_RATIOS)
            inst = self._pick(FINANCE_INSTITUTIONS)
            return Example(
                id=f"finance-gen-tp-{idx:03d}",
                text=f"The leveraged buyout closed at {ratio} with mezzanine financing from {inst}.",
                expected_entities=[{"type": "LEVERAGE_RATIO"}, {"type": "INSTITUTION_NAME"}],
                expected_level="HIGH", category="true_positive",
                notes=f"Leverage ratio + institution — gen {idx}",
            )
        elif t == 6:
            years = self._rng.randint(3, 7)
            return Example(
                id=f"finance-gen-tp-{idx:03d}",
                text=f"Distribution restrictions: this LP cannot distribute capital until the {years}th anniversary.",
                expected_entities=[{"type": "DISTRIBUTION_RESTRICTION"}],
                expected_level="HIGH", category="true_positive",
                notes=f"LP distribution restriction — gen {idx}",
            )
        elif t == 7:
            direction = self._pick(["miss", "beat"])
            amount = f"${self._rng.uniform(0.03, 0.25):.2f}"
            return Example(
                id=f"finance-gen-tp-{idx:03d}",
                text=f"Material non-public — earnings will {direction} consensus by {amount} per share.",
                expected_entities=[{"type": "MNPI_MARKER"}],
                expected_level="CRITICAL", category="true_positive",
                notes=f"MNPI earnings — gen {idx}",
            )
        elif t == 8:
            inst = self._pick(FINANCE_INSTITUTIONS)
            day = self._pick(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
            return Example(
                id=f"finance-gen-tp-{idx:03d}",
                text=f"Insider tip from a contact at {inst}: the deal will be announced {day} morning.",
                expected_entities=[{"type": "INSIDER_MARKER"}, {"type": "INSTITUTION_NAME"}],
                expected_level="CRITICAL", category="true_positive",
                notes=f"Insider tip + institution — gen {idx}",
            )
        else:
            r1 = self._pick(LEVERAGE_RATIOS)
            r2 = self._pick([r for r in LEVERAGE_RATIOS if r != r1])
            return Example(
                id=f"finance-gen-tp-{idx:03d}",
                text=f"Covenant package on the term loan: max {r1}, no distributions while ratio > {r2}.",
                expected_entities=[{"type": "LEVERAGE_RATIO"}, {"type": "DISTRIBUTION_RESTRICTION"}],
                expected_level="HIGH", category="true_positive",
                notes=f"Covenant + leverage + restriction — gen {idx}",
            )

    def _finance_tn(self, idx: int) -> Example:
        t = idx % 4
        if t == 0:
            deal1 = self._pick(["leveraged buyout", "management buyout", "strategic acquisition"])
            deal2 = self._pick(["merger", "joint venture", "spinoff", "carve-out"])
            return Example(
                id=f"finance-gen-tn-{idx:03d}",
                text=f"What's the difference between a {deal1} and a {deal2}?",
                expected_entities=[], expected_level="NONE", category="true_negative",
                notes="Generic finance question",
            )
        elif t == 1:
            concept = self._pick(["carry waterfall", "IRR", "MOIC", "fund economics"])
            fund_type = self._pick(["PE", "VC", "credit", "real estate"])
            return Example(
                id=f"finance-gen-tn-{idx:03d}",
                text=f"Can you explain how {concept} works in a typical {fund_type} fund?",
                expected_entities=[], expected_level="NONE", category="true_negative",
                notes="Educational PE/finance question",
            )
        elif t == 2:
            direction = self._pick(["up", "down", "flat"])
            pct = round(self._rng.uniform(0.1, 3.0), 1)
            driver = self._pick(["positive jobs data", "CPI reading", "Fed comments", "earnings reports"])
            return Example(
                id=f"finance-gen-tn-{idx:03d}",
                text=f"The market closed {direction} {pct}% today on {driver}.",
                expected_entities=[], expected_level="NONE", category="true_negative",
                notes="Public market commentary",
            )
        else:
            entity = self._pick(["Berkshire Hathaway", "JPMorgan", "Goldman Sachs", "Bridgewater"])
            doc = self._pick(["annual letter to shareholders", "10-K", "earnings call", "investor day"])
            return Example(
                id=f"finance-gen-tn-{idx:03d}",
                text=f"Please summarize {entity}'s {doc}.",
                expected_entities=[], expected_level="NONE", category="true_negative",
                notes="Public information reference",
            )

    def _finance_adv(self, idx: int) -> Example:
        t = idx % 4
        if t == 0:
            product = self._pick(["product", "service", "feature", "release"])
            version = self._pick(["prior generation", "previous version", "earlier model"])
            return Example(
                id=f"finance-gen-adv-{idx:03d}",
                text=f"The new {product} is a material improvement over the {version}.",
                expected_entities=[], expected_level="NONE", category="adversarial_negative",
                notes="'material' in non-financial context",
            )
        elif t == 1:
            item = self._pick(["marketing software", "cloud infrastructure", "HR tools"])
            period = self._pick(["next quarter", "next year", "this fiscal year"])
            return Example(
                id=f"finance-gen-adv-{idx:03d}",
                text=f"We're looking at acquisition costs for {item} {period}.",
                expected_entities=[], expected_level="LOW", category="adversarial_negative",
                notes="'acquisition' in cost-accounting context",
            )
        elif t == 2:
            context = self._pick(["the team's lunch plans", "the office holiday party", "the team outing"])
            return Example(
                id=f"finance-gen-adv-{idx:03d}",
                text=f"Insider information about {context}: it's been confirmed.",
                expected_entities=[], expected_level="LOW", category="adversarial_negative",
                notes="'insider information' used colloquially",
            )
        else:
            noun = self._pick(["knowledge", "experience", "talent", "creativity"])
            org = self._pick(["team", "organisation", "company", "department"])
            return Example(
                id=f"finance-gen-adv-{idx:03d}",
                text=f"The fund of {noun} in this {org} is impressive.",
                expected_entities=[], expected_level="NONE", category="adversarial_negative",
                notes="'fund' in idiomatic English",
            )

    # ── Public API ─────────────────────────────────────────────────────────

    def generate_legal(self, per_domain: int) -> list[Example]:
        tp_count = int(per_domain * 0.60)
        tn_count = int(per_domain * 0.20)
        adv_count = per_domain - tp_count - tn_count
        examples = (
            [self._legal_tp(i + 1) for i in range(tp_count)]
            + [self._legal_tn(i + 1) for i in range(tn_count)]
            + [self._legal_adv(i + 1) for i in range(adv_count)]
        )
        self._rng.shuffle(examples)
        return examples

    def generate_therapy(self, per_domain: int) -> list[Example]:
        tp_count = int(per_domain * 0.60)
        tn_count = int(per_domain * 0.20)
        adv_count = per_domain - tp_count - tn_count
        examples = (
            [self._therapy_tp(i + 1) for i in range(tp_count)]
            + [self._therapy_tn(i + 1) for i in range(tn_count)]
            + [self._therapy_adv(i + 1) for i in range(adv_count)]
        )
        self._rng.shuffle(examples)
        return examples

    def generate_finance(self, per_domain: int) -> list[Example]:
        tp_count = int(per_domain * 0.60)
        tn_count = int(per_domain * 0.20)
        adv_count = per_domain - tp_count - tn_count
        examples = (
            [self._finance_tp(i + 1) for i in range(tp_count)]
            + [self._finance_tn(i + 1) for i in range(tn_count)]
            + [self._finance_adv(i + 1) for i in range(adv_count)]
        )
        self._rng.shuffle(examples)
        return examples


# ── I/O ───────────────────────────────────────────────────────────────────────

def write_jsonl(examples: list[Example], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex.to_dict()) + "\n")


def print_stats(domain: str, examples: list[Example]) -> None:
    tp = sum(1 for e in examples if e.category == "true_positive")
    tn = sum(1 for e in examples if e.category == "true_negative")
    adv = sum(1 for e in examples if e.category == "adversarial_negative")
    total = len(examples)
    print(
        f"  {domain:12s}: {total:4d} total  "
        f"TP={tp} ({tp / total * 100:.0f}%)  "
        f"TN={tn} ({tn / total * 100:.0f}%)  "
        f"ADV={adv} ({adv / total * 100:.0f}%)"
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory to write expanded JSONL files (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--per-domain",
        type=int,
        default=DEFAULT_PER_DOMAIN,
        help=f"Number of examples to generate per domain (default: {DEFAULT_PER_DOMAIN})",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"RNG seed for deterministic output (default: {DEFAULT_SEED})",
    )
    args = parser.parse_args()

    if args.per_domain < 50:
        parser.error("--per-domain must be >=50 to maintain meaningful class balance")

    gen = CorpusGenerator(seed=args.seed)

    print(f"Generating eval corpus (per_domain={args.per_domain}, seed={args.seed})...")
    legal = gen.generate_legal(args.per_domain)
    therapy = gen.generate_therapy(args.per_domain)
    finance = gen.generate_finance(args.per_domain)

    print("Stats:")
    print_stats("legal", legal)
    print_stats("therapy", therapy)
    print_stats("finance", finance)
    total = len(legal) + len(therapy) + len(finance)
    print(f"  {'TOTAL':12s}: {total:4d} examples")

    write_jsonl(legal, args.output_dir / "legal_privilege_expanded.jsonl")
    write_jsonl(therapy, args.output_dir / "therapy_phi_expanded.jsonl")
    write_jsonl(finance, args.output_dir / "finance_mnpi_expanded.jsonl")

    print(f"\nCorpus written to {args.output_dir}/")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())


__all__ = ["CorpusGenerator", "Example", "write_jsonl"]
