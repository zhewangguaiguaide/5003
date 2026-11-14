# CORE20 Public Question List

Date: 2026-11-03  
Status: draft candidate; query-only publication for team review.  
Corpus SHA256: `2c3f9a2d9dc116062791e8c646ad7e343fd8e22f5a59c91581f84808b0620752`

> This file contains questions and public retrieval status only. Required facts, gold evidence,
> expected answers and private scoring assets remain in `evals/private/` and are not published.
> Because the test items are now public, later generalization checks must use an independent,
> previously unseen question set.

| ID | Topic | Question | rerank@50 Hit@5 | First rank |
|---|---|---|---:|---:|
| `CORE-ADM-001` | 申请 | As an exchange applicant, where should I send my application and what should I confirm before submitting it? | Y | 1 |
| `CORE-ADM-002` | 申请 | When should an inbound exchange applicant normally receive the letter of acceptance for September entry? | Y | 2 |
| `CORE-CAL-001` | 校历与重要日期 | What is the last day for course add/drop in Semester A 2026/27? | Y | 1 |
| `CORE-CAL-002` | 校历与重要日期 | When is the Semester B 2026/27 examination period? | Y | 3 |
| `CORE-FEE-001` | 学费与缴费 | If my leave of absence is approved, how much continuation fee is charged per semester and in Summer? | Y | 1 |
| `CORE-FEE-002` | 学费与缴费 | What late payment charge applies to an overdue student account? | N | — |
| `CORE-FEE-003` | 学费与缴费 | After a tuition overpayment refund is approved and valid bank details are provided, how long does the Finance Office normally take to release it? | Y | 1 |
| `CORE-LIB-001` | 图书馆 | Where can I renew books that I have checked out? | Y | 1 |
| `CORE-LIB-002` | 图书馆 | What happens if a checked-out book is recalled, and are late returns charged? | Y | 1 |
| `CORE-LIB-003` | 图书馆 | What identification is required to enter the Library and borrow items? | Y | 1 |
| `CORE-SCH-001` | 奖学金与助学金 | How are non-local entrance scholarships awarded, and do I need to submit a separate application? | Y | 3 |
| `CORE-SCH-002` | 奖学金与助学金 | Who may apply for the CityUHK Emergency Fund, when can they apply, and is an appointment needed? | Y | 1 |
| `CORE-REG-001` | 注册与学籍 | I am a full-time student who needs to take fewer than 12 credits due to special circumstances. How do I apply? | Y | 5 |
| `CORE-REG-002` | 注册与学籍 | Can I drop a course after the add/drop deadline, and what grade may appear if the late drop is approved? | N | — |
| `CORE-REG-003` | 注册与学籍 | What are the maximum transferable credits for a normative four-year degree and for Advanced Standing II? | Y | 3 |
| `CORE-RES-001` | 宿舍 | When is the 2026/27 hall application period for a new non-local international undergraduate student at the Ma On Shan Compound? | N | — |
| `CORE-RES-002` | 宿舍 | If I need a double room for single occupancy for medical reasons, what documents are required and what hall charge applies if approved? | Y | 2 |
| `CORE-VIS-001` | 签证与国际学生服务 | How many credits must a non-local student register for in a regular semester and in Summer to maintain full-time status? | Y | 3 |
| `CORE-VIS-002` | 签证与国际学生服务 | What visa or entry permit must I obtain before studying in Hong Kong if I do not have the right of abode or right to land? | Y | 1 |
| `CORE-VIS-003` | 签证与国际学生服务 | What insurance requirement applies to non-local students throughout their studies at CityUHK? | Y | 2 |

## Machine-readable file

`core20_questions_20261103.jsonl` contains `case_id`, `topic`, `query`, `persona`, `as_of`,
`rerank50_hit_at_5` and `rerank50_first_relevant_rank`. It contains no gold fields.
