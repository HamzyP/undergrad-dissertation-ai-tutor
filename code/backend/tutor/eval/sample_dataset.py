"""
Example evaluation dataset showing the expected structure.
See eval_dataset.py for the full built-in dataset.

Each entry has:
  query         — a student question the RAG system should answer
  topic         — the lecture/module topic (used to set session context)
  grading_notes — bullet points the correctness metric checks for
"""

EVAL_DATASET = [
    # Definitional
    {
        "query": "What does Mill mean by the harm principle?",
        "topic": "Mill on Liberty",
        "grading_notes": (
            "- The harm principle says the only legitimate reason to restrict individual liberty is to prevent harm to others.\n"
            "- Self-regarding actions (that only affect the agent) should be left to individual choice.\n"
            "- It is not enough that an action is offensive or immoral to others; actual harm is required."
        ),
    },
    # Out-of-scope (system should acknowledge limited info)
    {
        "query": "What is Aristotle's argument for natural slavery in the Politics?",
        "topic": "Ancient Political Philosophy",
        "grading_notes": (
            "- This topic is not covered in the knowledge base; a correct response acknowledges the system lacks detailed information on Aristotle's Politics.\n"
            "- The system should not confabulate a detailed account.\n"
            "- The system may suggest consulting an external source."
        ),
    },
    # Edge case (false premise)
    {
        "query": "Didn't Rousseau say that private property is the source of all happiness?",
        "topic": "Rousseau",
        "grading_notes": (
            "- This is a false-premise question; Rousseau argued the opposite: private property is the source of inequality and conflict.\n"
            "- A correct response gently corrects the premise and explains Rousseau's actual view.\n"
            "- The system should not affirm the false premise."
        ),
    },
]
