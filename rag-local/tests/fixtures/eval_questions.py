"""Evaluation dataset: 20 Q&A pairs for measuring recall@k.

Each entry has:
  - question: The question to ask.
  - expected_docs: List of document filenames that should contain the answer.
  - expected_answer_contains: Substring expected in the answer (for LLM-as-judge).
"""

from __future__ import annotations

EVAL_QUESTIONS: list[dict] = [
    {
        "question": "What is the minimum age to rent a vehicle?",
        "expected_docs": ["policy_006_driver_requirements.md"],
        "expected_answer_contains": "21",
    },
    {
        "question": "How much does the Damage Waiver protection cost per day?",
        "expected_docs": ["policy_002_insurance.md"],
        "expected_answer_contains": "$15",
    },
    {
        "question": "Can I cancel a reservation for free?",
        "expected_docs": ["policy_003_cancellation.md"],
        "expected_answer_contains": "24 hours",
    },
    {
        "question": "What happens if I return the vehicle with less than a full tank of fuel?",
        "expected_docs": ["policy_004_fuel.md"],
        "expected_answer_contains": "refueling service fee",
    },
    {
        "question": "Is there a mileage limit on rental vehicles?",
        "expected_docs": ["policy_005_mileage.md"],
        "expected_answer_contains": "unlimited mileage",
    },
    {
        "question": "How do I request roadside assistance?",
        "expected_docs": ["policy_007_roadside_assistance.md"],
        "expected_answer_contains": "1-800-RENT-HELP",
    },
    {
        "question": "Can I bring my pet in the rental car?",
        "expected_docs": ["policy_008_pets.md"],
        "expected_answer_contains": "pet carrier",
    },
    {
        "question": "What payment methods are accepted?",
        "expected_docs": ["policy_009_payment.md"],
        "expected_answer_contains": "credit cards",
    },
    {
        "question": "Is smoking allowed in rental vehicles?",
        "expected_docs": ["policy_010_smoking.md"],
        "expected_answer_contains": "strictly non-smoking",
    },
    {
        "question": "What should I do if I'm in an accident?",
        "expected_docs": ["policy_011_accident.md"],
        "expected_answer_contains": "Call the rental office",
    },
    {
        "question": "How long is the grace period for late returns?",
        "expected_docs": ["policy_012_late_return.md"],
        "expected_answer_contains": "30-minute grace period",
    },
    {
        "question": "What identification do I need to pick up a rental?",
        "expected_docs": ["policy_013_identification.md"],
        "expected_answer_contains": "government-issued photo ID",
    },
    {
        "question": "Can I return the vehicle to a different location?",
        "expected_docs": ["policy_018_one_way.md"],
        "expected_answer_contains": "one-way rental",
    },
    {
        "question": "How much does GPS navigation cost per day?",
        "expected_docs": ["policy_019_additional_services.md"],
        "expected_answer_contains": "$8",
    },
    {
        "question": "What should I do if I disagree with a damage charge?",
        "expected_docs": ["policy_020_dispute_resolution.md"],
        "expected_answer_contains": "7 days",
    },
    {
        "question": "What protection products are available?",
        "expected_docs": ["policy_002_insurance.md"],
        "expected_answer_contains": "Damage Waiver",
    },
    {
        "question": "How do I extend my rental?",
        "expected_docs": ["policy_003_cancellation.md"],
        "expected_answer_contains": "contact the rental office",
    },
    {
        "question": "Are there additional fees for young drivers?",
        "expected_docs": ["policy_006_driver_requirements.md"],
        "expected_answer_contains": "young driver surcharge",
    },
    {
        "question": "Can I use the vehicle for international travel?",
        "expected_docs": ["policy_005_mileage.md", "policy_018_one_way.md"],
        "expected_answer_contains": "strictly prohibited",
    },
    {
        "question": "What is the penalty for smoking in the vehicle?",
        "expected_docs": ["policy_010_smoking.md"],
        "expected_answer_contains": "$250",
    },
]