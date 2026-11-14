# Agent Response and Citation Evaluation — Method Draft

Status: method prepared; calibration, human confirmation and formal answer-quality results pending. Section numbering follows the group's final report matrix; this draft does not settle ownership of full-report editing.

## Evaluation objective and scope

The response evaluation examines whether the application answers student-service questions using applicable evidence, retains necessary conditions and exceptions, cites supporting passages, and handles missing information or failed tools safely. Retrieval quality and response quality are reported separately. A relevant page URL alone is insufficient: the actual retrieved and supplied chunk must support the asserted fact.

## Cases and source control

Role4 and role6 share case identifiers, evidence references and version bindings. Source-grounded development cases are used to calibrate annotation and scoring. Clarification, absent evidence, personal status, tool failure and conflicting-policy scenarios are evaluated separately from the positive retrieval denominator. Fault fixtures are explicitly labelled and isolated from the production corpus. Related variants are not counted as independent samples.

Each answerable case specifies atomic required facts, applicability conditions, sufficient evidence combinations and forbidden claims. Expected actions distinguish answering, clarifying and referring or abstaining. Ambiguous or conflicting cases remain candidates until their schema and behavior have been agreed. Development cases and their underlying facts must not be reused as unseen CORE cases. Gold annotations, expected actions and scores remain evaluator-side; only user-known query conditions are supplied to the tested system.

## Rubric and review

The rubric assesses correctness (40%), completeness (25%), citation support (25%) and clarity with an appropriate next action (10%). Each dimension uses anchors from zero to four with examples. Missing runtime results remain null and unrun. An inapplicable dimension requires an explanation; applicable weights are normalized, and comparisons identify the dimension set used.

Critical unsupported claims about fees, deadlines, eligibility or visa status, invented personal outcomes, fabricated official sources and unsafe credential requests are blocking failures. Weighted scores cannot offset them. Reviewers verify additional assertions even when they are absent from the reference wording. Appropriate clarification or referral is not penalized for failing to provide a policy conclusion unsupported by available evidence.

Role4 and role6 independently assess calibration outputs and resolve recorded disagreements. AI-assisted preparation does not constitute either reviewer's independent sign-off. On 14 November 2026, role6 confirmed agreement with all ten YP-DEV cases and all five YP-NR cases in the local v1 delivery. Role4 review remains pending. This personal confirmation does not freeze CORE or establish joint review.

## Execution, diagnosis and limitations

Actual answers, citations, retrieval rounds, final context IDs, tool events and version information must be retained. Review distinguishes retrieval gaps from generation errors, condition omissions, unsupported citations, inappropriate refusals and failed degradation. Tool errors are tested with controlled fixtures and explicit budgets, without altering the official corpus.

No answer-quality figures are reported in this draft. Existing CORE20 retrieval candidate results cannot be substituted for response accuracy or formal acceptance. Current limitations include small calibration samples, snapshot-versus-current-policy differences, unavailable private CORE traces and pending backend fault-injection support. Formal results and charts will be added only after matched-version execution and review.
